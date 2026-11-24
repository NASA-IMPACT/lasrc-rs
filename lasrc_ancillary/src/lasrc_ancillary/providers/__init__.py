"""Ancillary data providers, one subpackage per source.

Each provider's package and its ``fetch`` module use only the standard library, so the
orchestration can import them in a Lambda. Conversion to the interchange file lives in the
provider's ``convert`` module, which needs the provider's extra.
"""
