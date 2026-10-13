# from django.http import HttpResponse
# from django.template import loader

from django.http import JsonResponse


def health_check(request):
    """Liveness probe for the App Service health check.

    Deliberately does not touch the database: a transient DB blip would mark the
    instance unhealthy and trigger container restarts that cannot fix it.
    """
    return JsonResponse({"status": "ok"})
