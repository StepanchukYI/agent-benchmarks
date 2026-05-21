"""Example module with three public functions and one private helper."""


def alpha():
    return _private("alpha")


def beta(value):
    return _private(value)


def gamma(left, right):
    return _private(left) + _private(right)


def _private(token):
    return f"widget::{token}"
