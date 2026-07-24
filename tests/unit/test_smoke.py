import birec


def test_package_imports() -> None:
    assert birec is not None


def test_version_is_defined() -> None:
    assert isinstance(birec.__version__, str)
    assert birec.__version__
