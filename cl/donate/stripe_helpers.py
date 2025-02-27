import json
import logging
import time
from datetime import datetime

import stripe
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponseNotAllowed, HttpResponse
from django.utils.timezone import utc
from django.views.decorators.csrf import csrf_exempt

from cl.donate.models import Donation, PROVIDERS
from cl.donate.utils import send_thank_you_email, PaymentFailureException
from cl.users.utils import create_stub_account

logger = logging.getLogger(__name__)


def handle_xero_payment(charge):
    """Gather data from a callback triggered by a payment in Xero

    When we send invoices to folks via Xero, they now have the option to make
    a payment via Stripe. When they do, it triggers our callback, but when that
    happens we don't know anything about the charge.

    To address this, gather data from the Stripe charge, add a user and a
    donation to the database.

    :param charge: A Stripe charge object: https://stripe.com/docs/api/charges
    :return: None
    """
    billing_details = charge['billing_details']
    email = billing_details['email']
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        user, _ = create_stub_account({
            'email': email,
            # Stripe doesn't split up first/last name (smart), but we
            # do (doh). Just stuff it in the first_name field.
            'first_name': billing_details['name'],
            'last_name': '',
        }, {
            'address1': billing_details['address']['line1'],
            'address2': billing_details['address']['line2'],
            'city': billing_details['address']['city'],
            'state': billing_details['address']['state'],
            'zip_code': billing_details['address']['postal_code'],
            'wants_newsletter': False,
        })
    Donation.objects.create(
        donor=user,
        amount=float(charge['amount']) / 100,  # Stripe does pennies.
        payment_provider=PROVIDERS.CREDIT_CARD,
        payment_id=charge['id'],
        status=Donation.AWAITING_PAYMENT,
        referrer='XERO invoice number: %s' %
                 charge['metadata']['Invoice number'],
    )


@csrf_exempt
def process_stripe_callback(request):
    """Always return 200 message or else the webhook will try again ~200 times
    and then send us an email.
    """
    if request.method == 'POST':
        # Stripe hits us with a callback, and their security model is for us
        # to use the ID from that to hit their API. It's analogous to when you
        # get a random call and you call them back to make sure it's legit.
        event_id = json.loads(request.body)['id']
        # Now use the API to call back.
        stripe.api_key = settings.STRIPE_SECRET_KEY
        event = json.loads(str(stripe.Event.retrieve(event_id)))
        logger.info('Stripe callback triggered with event id of %s. See '
                    'webhook documentation for details.', event_id)
        if event['type'].startswith('charge') and \
                event['livemode'] != settings.PAYMENT_TESTING_MODE:
            charge = event['data']['object']

            if charge['application'] == settings.XERO_APPLICATION_ID:
                handle_xero_payment(charge)

            # Sometimes stripe can process a transaction and call our callback
            # faster than we can even save things to our own DB. If that
            # happens wait a second up to five times until it works.
            retry_count = 5
            d = None
            while retry_count > 0:
                try:
                    d = Donation.objects.get(payment_id=charge['id'])
                except Donation.DoesNotExist:
                    time.sleep(1)
                    retry_count -= 1
                else:
                    break

            # See: https://stripe.com/docs/api#event_types
            if event['type'].endswith('succeeded'):
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.PROCESSED
                if charge['application'] == settings.XERO_APPLICATION_ID:
                    # Don't send thank you's for Xero invoices
                    pass
                else:
                    payment_type = charge['metadata']['type']
                    if charge['metadata'].get('recurring'):
                        send_thank_you_email(d, payment_type, recurring=True)
                    else:
                        send_thank_you_email(d, payment_type)
            elif event['type'].endswith('failed'):
                if not d:
                    return HttpResponse('<h1>200: No matching object in the '
                                        'database. No action needed.</h1>')
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.AWAITING_PAYMENT
            elif event['type'].endswith('refunded'):
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.RECLAIMED_REFUNDED
            elif event['type'].endswith('captured'):
                d.clearing_date = datetime.utcfromtimestamp(
                    charge['created']).replace(tzinfo=utc)
                d.status = Donation.CAPTURED
            elif event['type'].endswith('dispute.created'):
                logger.critical("Somebody has created a dispute in "
                                "Stripe: %s" % charge['id'])
            elif event['type'].endswith('dispute.updated'):
                logger.critical("The Stripe dispute on charge %s has been "
                                "updated." % charge['id'])
            elif event['type'].endswith('dispute.closed'):
                logger.critical("The Stripe dispute on charge %s has been "
                                "closed." % charge['id'])
            d.save()
        return HttpResponse('<h1>200: OK</h1>')
    else:
        return HttpResponseNotAllowed(
            permitted_methods={'POST'},
            content='<h1>405: This is a callback endpoint for a payment '
                    'provider. Only POST methods are allowed.</h1>'
        )


def process_stripe_payment(amount, email, kwargs, stripe_redirect_url):
    """Process a stripe payment.

    :param amount: The amount, in pennies, that you wish to charge
    :param email: The email address of the person being charged
    :param kwargs: Keyword arguments to pass to Stripe's `create` method. Some
    functioning options for this dict are:

        {'card': stripe_token}

    And:

        {'customer': customer.id}

    Where stripe_token is a token returned by Stripe's client-side JS library,
    and customer is an object returned by stripe's customer creation server-
    side library.

    :param stripe_redirect_url: Where to send the user after a successful
    transaction
    :return: response object with information about whether the transaction
    succeeded.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Create the charge on Stripe's servers
    try:
        charge = stripe.Charge.create(
            amount=amount,
            currency="usd",
            description=email,
            **kwargs
        )
        response = {
            'status': Donation.AWAITING_PAYMENT,
            'payment_id': charge.id,
            'redirect': stripe_redirect_url,
        }
    except (stripe.error.CardError, stripe.error.InvalidRequestError) as e:
        logger.warn("Stripe was unable to process the payment: %s" % e)
        message = ('Oops, we had an error with your donation: '
                   '<strong>%s</strong>' % e.json_body['error']['message'])
        raise PaymentFailureException(message)

    return response


def create_stripe_customer(source, email):
    """Create a stripe customer so that we can charge this person more than
    once
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        return stripe.Customer.create(source=source, email=email)
    except (stripe.error.CardError, stripe.error.InvalidRequestError) as e:
        logger.warn("Stripe was unable to create the customer: %s" % e)
        message = ('Oops, we had an error with your donation: '
                   '<strong>%s</strong>' % e.json_body['error']['message'])
        raise PaymentFailureException(message)
