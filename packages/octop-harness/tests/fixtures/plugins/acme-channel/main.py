"""Example channel plugin: contributes the ``acme`` channel kind."""


class AcmeChannel:
    """Minimal stand-in for a real gateway channel class."""

    channel_type = "acme"


def setup(ctx) -> None:
    ctx.channel(
        "acme",
        AcmeChannel,
        label="Acme IM",
        intro_url="https://example.com/acme",
        fields=[
            {"name": "token", "label": "Token", "type": "password", "required": True},
            {"name": "endpoint", "label": "Endpoint", "placeholder": "https://acme.example/api"},
        ],
    )
