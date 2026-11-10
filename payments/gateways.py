"""Payment gateway extension point.

No provider adapter is enabled in v0.7. Do not use a browser redirect or
an unsigned callback to mark a merchant payment successful.
"""


class ProviderNotConnected(RuntimeError):
    pass


def initiate_online_payment(*args, **kwargs):
    raise ProviderNotConnected('No approved provider adapter is configured. Manual orders only.')


def verify_payment_webhook(*args, **kwargs):
    raise ProviderNotConnected('Signed payment webhooks are not enabled yet.')
