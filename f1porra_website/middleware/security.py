"""Custom security middleware for additional protection."""

import re
from django.http import HttpResponseForbidden
from django.conf import settings


class SecurityHeadersMiddleware:
    """Add security headers to all responses."""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Content Security Policy
        if not settings.DEBUG:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://use.fontawesome.com https://cdn.startbootstrap.com https://code.highcharts.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com https://use.fontawesome.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
        
        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response


class SQLInjectionProtectionMiddleware:
    """Additional layer of SQL injection protection.
    
    Note: Django's ORM already provides SQL injection protection through
    parameterized queries. This middleware only checks URL query strings
    for obvious attack patterns, not POST body data (which would cause
    false positives on legitimate form submissions).
    """
    
    # Only check for very specific attack patterns in query strings
    SQL_PATTERNS = [
        r"((\%27)|(\'))(\s*)(union|select|insert|update|delete|drop)",
        r"exec(\s|\+)+(s|x)p\w+",
        r";\s*(drop|delete|truncate)\s+",
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.SQL_PATTERNS]

    def __call__(self, request):
        # Only check query string (URL parameters) - not POST body
        # POST bodies are protected by CSRF and Django ORM already
        query_string = request.META.get('QUERY_STRING', '')
        if query_string and self._contains_sql_injection(query_string):
            return HttpResponseForbidden('Forbidden')
        
        return self.get_response(request)
    
    def _contains_sql_injection(self, text):
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False
