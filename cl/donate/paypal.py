import logging
from urlparse import urlparse, parse_qs

import requests
import simplejson as json  # This is needed to handle Decimal objects.
from django.conf import settings
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from rest_framework.status import HTTP_201_CREATED, HTTP_200_OK

from cl.donate.models import Donation, PAYMENT_TYPES
from cl.donate.utils import send_thank_you_email, PaymentFailureException

logger = logging.getLogger(__name__)


def get_paypal_access_token():
    """Get a token for the PayPal API.

    Query the PayPal API to get an access token. This could be improved by
    caching the token and detecting when it is expired.
    """
    r = requests.post(
        '%s/v1/oauth2/token' % settings.PAYPAL_ENDPOINT,
        headers={
            'Accept': 'application/json',
            'Accept-Language': 'en_US'
        },
        auth=(
            settings.PAYPAL_CLIENT_ID,
            settings.PAYPAL_SECRET_KEY,
        ),
        data={'grant_type': 'client_credentials'}
    )
    if r.status_code == HTTP_200_OK:
        logger.info("Got paypal token successfully.")
    else:
        logger.critical("Problem getting paypal token status_code was: %s, "
                        "with content: %s" % (r.status_code, r.content))
    return json.loads(r.content).get('access_token')


@csrf_exempt
def process_paypal_callback(request):
    """Process the GET request that PayPal uses.

    After a transaction is completed, PayPal sends the user back to a page on
    our site. This could be our "Thanks" page, but since that page is seen by
    all the payment providers, instead this is an intermediate page, where we
    grab the correct things from the URL, process the item, and then shuttle
    the user off to the normal "Thanks" page.

    The other providers do this via a POST rather than a GET, so that's why
    this one is a bit of an oddball.
    """
    access_token = get_paypal_access_token()
    d = Donation.objects.get(transaction_id=request.GET['token'])
    r = requests.post(
        '%s/v1/payments/payment/%s/execute/' % (
            settings.PAYPAL_ENDPOINT,
            d.payment_id
        ),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % access_token
        },
        data=json.dumps({'payer_id': request.GET['PayerID']}),
    )
    if r.status_code == HTTP_200_OK:
        d.clearing_date = now()
        # Technically, this should be d.status = 2 (Completed, awaiting
        # processing) and we should await a webhook to tell us that the
        # processing completed successfully (4). Alas, PayPal is so terrible
        # that I can't figure that out, so we just assume that if it gets
        # completed (2), it'll get processed (4).
        d.status = Donation.PROCESSED
        d.save()
        send_thank_you_email(d, payment_type=PAYMENT_TYPES.DONATION)
    else:
        logger.critical("Unable to execute PayPal transaction. Status code %s "
                        "with data: %s" % (r.status_code, r.content))
        d.status = Donation.UNKNOWN_ERROR
        d.save()
    # Finally, show them the thank you page
    return HttpResponseRedirect(reverse('donate_complete'))


def process_paypal_payment(cd_donation_form):
    # https://developer.paypal.com/webapps/developer/docs/integration/web/accept-paypal-payment/
    access_token = get_paypal_access_token()
    if not access_token:
        raise PaymentFailureException('NO_ACCESS_TOKEN')

    return_url = 'https://www.courtlistener.com%s' % reverse('paypal_callback')
    cancel_url = 'https://www.courtlistener.com%s' % reverse('paypal_cancel')
    data = {
        'intent': 'sale',
        'redirect_urls': {
            'return_url': return_url,
            'cancel_url': cancel_url,
        },
        'payer': {'payment_method': 'paypal'},
        'transactions': [
            {
                'amount': {
                    'total': cd_donation_form['amount'],
                    'currency': 'USD',
                },
                'description': 'Donation to Free Law Project',
            }
        ]
    }
    r = requests.post(
        '%s/v1/payments/payment' % settings.PAYPAL_ENDPOINT,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % access_token
        },
        data=json.dumps(data)
    )

    if r.status_code == HTTP_201_CREATED:
        r_content_as_dict = json.loads(r.content)
        # Get the redirect value from the 'links' attribute. Links look like:
        #   [{u'href': u'https://api.sandbox.paypal.com/v1/payments/payment/PAY-8BC403022U6413151KIQPC2I',
        #     u'method': u'GET',
        #     u'rel': u'self'},
        #    {u'href': u'https://www.sandbox.paypal.com/cgi-bin/webscr?cmd=_express-checkout&token=EC-6VV58324J9479725S',
        #     u'method': u'REDIRECT',
        #     u'rel': u'approval_url'},
        #    {u'href': u'https://api.sandbox.paypal.com/v1/payments/payment/PAY-8BC403022U6413151KIQPC2I/execute',
        #     u'method': u'POST',
        #     u'rel': u'execute'}
        #   ]
        redirect = [link for link in r_content_as_dict['links'] if
                    link['rel'].lower() == 'approval_url'][0]['href']
        parsed_redirect = urlparse(redirect)
        token = parse_qs(parsed_redirect.query)['token'][0]
        response = {
            'status': Donation.AWAITING_PAYMENT,
            'payment_id': r_content_as_dict.get('id'),
            'transaction_id': token,
            'redirect': redirect,
        }
        logger.info("Created payment in paypal with response: %s", response)
        return response
    else:
        raise PaymentFailureException("UNABLE_TO_MAKE_PAYMENT")


def donate_paypal_cancel(request):
    d = Donation.objects.get(transaction_id=request.GET['token'])
    d.status = Donation.CANCELLED
    d.save()

    return render(request, 'donate_complete.html', {
        'error': 'User Cancelled',
        'private': False,
    })
