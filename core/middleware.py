"""Project middleware."""
from django.utils.cache import patch_vary_headers


class PrivateAuthenticatedCacheMiddleware:
    """Never let a shared/edge cache store an authenticated response.

    The staff admin toolbar is rendered into the HTML for logged-in staff, so an
    authenticated page must never be cached and replayed to an anonymous visitor.
    For any authenticated request we force ``Cache-Control: private, no-store``
    and add ``Vary: Cookie``. Anonymous responses are left untouched, so public
    pages can still be cached at the edge.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            patch_vary_headers(response, ('Cookie',))
            response['Cache-Control'] = 'private, no-store, max-age=0'
        return response
