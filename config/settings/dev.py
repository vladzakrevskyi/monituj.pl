import warnings

from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Static files through WhiteNoise here too, instead of runserver's own
# handler: that one sends no Cache-Control, so browsers kept an old JS or
# CSS file after it changed. With DEBUG WhiteNoise sends max-age=0 and reads
# the files from static/ on every request - a reload always gets the
# current version.
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405
MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
# Files come straight from static/ - there is no collected staticfiles/ here.
warnings.filterwarnings("ignore", message="No directory at", category=UserWarning)
