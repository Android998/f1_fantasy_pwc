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
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://use.fontawesome.com https://cdn.startbootstrap.com; "
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
    """Additional layer of SQL injection protection."""
    
    # Patterns that might indicate SQL injection
    SQL_PATTERNS = [
        r"(\%27)|(\')|(\-\-)|(\%23)|(#)",
        r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",
        r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",
        r"((\%27)|(\'))union",
        r"exec(\s|\+)+(s|x)p\w+",
        r"UNION\s+SELECT",
        r"SELECT\s+.*\s+FROM",
        r"INSERT\s+INTO",
        r"DELETE\s+FROM",
        r"DROP\s+TABLE",
        r"UPDATE\s+.*\s+SET",
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.SQL_PATTERNS]

    def __call__(self, request):
        # Check query string
        query_string = request.META.get('QUERY_STRING', '')
        if self._contains_sql_injection(query_string):
            return HttpResponseForbidden('Forbidden')
        
        # Check POST data
        if request.method == 'POST':
            body = request.body.decode('utf-8', errors='ignore')
            if self._contains_sql_injection(body):
                return HttpResponseForbidden('Forbidden')
        
        return self.get_response(request)
    
    def _contains_sql_injection(self, text):
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False