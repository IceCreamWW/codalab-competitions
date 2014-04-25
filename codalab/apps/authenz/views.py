"""
View-related customatizations for auth.
"""

import json

from django.dispatch import receiver
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from allauth.account.signals import user_signed_up
from allauth.account.signals import user_logged_in

from oauth2_provider.models import AccessToken
from oauth2_provider.views.generic import ScopedProtectedResourceView

from apps.authenz.models import ClUser
from apps.authenz.oauth import get_or_create_cli_client

#
# Implements hooks for additional processing post sign-up and post log-in.
#

@receiver(user_signed_up)
def new_user_signup(sender, **kwargs):
    """
    Handles bookkeeping after a user signs up.
    """
    user = kwargs['user']
    get_or_create_cli_client(user)

@receiver(user_logged_in)
def on_user_logged_in(sender, **kwargs):
    """
    Handles bookkeeping after a user signs up.
    """
    user = kwargs['user']
    # Backwards compatibility: do this for user who signed up before OAuth was added.
    get_or_create_cli_client(user)

#
# OAuth token validation API
#

class ValidationApi(ScopedProtectedResourceView):
    """
    Translates an OAuth token into information about the associated CodaLab user.
    """
    required_scopes = ['token-validation']

    @staticmethod
    def _translate_token(token, scopes):
        """
        When users try to access resources, check that provided token is valid
        """
        if token is None or len(token) <= 0:
            return {'code': 400}
        try:
            access_token = AccessToken.objects.select_related("application", "user").get(token=token)
            if access_token.is_valid(scopes):
                return {
                    'code': 200,
                    'user': {'id': access_token.user.id, 'name': access_token.user.username}
                }
            return {'code': 403}
        except AccessToken.DoesNotExist:
            return {'code': 404}
        except:
            return {'code': 500}

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(ValidationApi, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        d = request.REQUEST
        token = d['token'] if 'token' in d else None
        scopes = d['scopes'] if 'scopes' in d else None
        response_data = ValidationApi._translate_token(token, scopes)
        return HttpResponse(json.dumps(response_data), content_type="application/json")


class InfoApi(ScopedProtectedResourceView):
    """
    Translates a list of names into information about CodaLab users with matching names.
    """
    required_scopes = ['token-validation']

    @staticmethod
    def _translate_names(names):
        """
        Performs translation of list of names to list of user dict.
        """
        if names is None or type(names) is not list or len(names) == 0:
            return {'code': 400}
        for name in names:
            if type(name) not in (str, unicode) or len(name) < 1:
                return {'code': 400}
        try:
            users = ClUser.objects.filter(username__in=names)
            user_dict = {}
            for user in users:
                user_dict[user.username] = user
            user_list = []
            for name in names:
                if name in user_dict:
                    user = user_dict[name]
                    user_list.append({'name': name, 'id': user.id, 'active': user.is_active})
                else:
                    user_list.append({'name': name})
            return {'code': 200, 'users': user_list}
        except:
            return {'code': 500}

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(InfoApi, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        names = request.POST.getlist('names') if 'names' in request.POST else None
        response_data = InfoApi._translate_names(names)
        return HttpResponse(json.dumps(response_data), content_type="application/json")
