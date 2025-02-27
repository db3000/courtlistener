from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponseNotAllowed, HttpResponse
from django.shortcuts import get_object_or_404, HttpResponseRedirect, render

from cl.alerts.models import Alert, DocketAlert
from cl.lib.ratelimiter import ratelimit_if_not_whitelisted


@login_required
def edit_alert_redirect(request, alert_id):
    """Note that this method is still very useful because it gives people an
    opportunity to login if they come to the site via one of our email alerts.
    """
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(
        Alert,
        pk=alert_id,
        user=request.user
    )
    return HttpResponseRedirect('/?%s&edit_alert=%s' % (alert.query, alert.pk))


@login_required
def delete_alert(request, pk):
    try:
        pk = int(pk)
    except ValueError:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(Alert, pk=pk, user=request.user)

    # if they've made it this far, they have permission to edit the alert
    alert.delete()
    messages.add_message(
        request,
        messages.SUCCESS,
        "Your alert <strong>%s</strong> was deleted successfully." % alert.name
    )
    return HttpResponseRedirect(reverse("profile_alerts"))


@login_required
def delete_alert_confirm(request, alert_id):
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect('/')
    return render(request, 'delete_confirm.html', {
        'alert_id': alert_id,
        'private': False
    })


@ratelimit_if_not_whitelisted
def disable_alert(request, secret_key):
    """Disable an alert based on a secret key."""
    alert = get_object_or_404(Alert, secret_key=secret_key)
    prev_rate = alert.rate
    alert.rate = Alert.OFF
    alert.save()
    return render(request, 'disable_alert.html', {
        'alert': alert,
        'prev_rate': prev_rate,
        'private': True,
    })


@ratelimit_if_not_whitelisted
def enable_alert(request, secret_key):
    alert = get_object_or_404(Alert, secret_key=secret_key)
    rate = request.GET.get('rate')
    if not rate:
        failed = "a rate was not provided"
    else:
        if rate not in Alert.ALL_FREQUENCIES:
            failed = "an unknown rate was provided"
        else:
            alert.rate = rate
            alert.save()
            failed = ''
    return render(request, 'enable_alert.html', {
        'alert': alert,
        'failed': failed,
        'private': True,
    })


def toggle_docket_alert(request):
    """Use Ajax to create or delete an alert for a user."""
    if request.is_ajax() and request.method == 'POST':
        docket_pk = request.POST.get('id')
        existing_alert = DocketAlert.objects.filter(user=request.user,
                                                    docket_id=docket_pk)
        if existing_alert.exists():
            existing_alert.delete()
            msg = "Alert disabled successfully"
        else:
            DocketAlert.objects.create(docket_id=docket_pk, user=request.user)
            msg = "Alerts are now enabled for this docket"
        return HttpResponse(msg)
    else:
        return HttpResponseNotAllowed(permitted_methods={'POST'},
                                      content="Not an ajax POST request.")
