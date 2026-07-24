"""Reusable design-pattern base classes."""

from __future__ import annotations

from typing import ClassVar, cast, final

__all__ = ("Singleton",)


class Singleton:
    """Base class providing a per-subclass singleton via :meth:`get_instance`."""

    _instances: ClassVar[dict[type[Singleton], Singleton]] = {}

    @final
    @classmethod
    def get_instance[T: Singleton](cls: type[T]) -> T:
        if cls is Singleton:
            raise TypeError("Singleton is abstract and cannot be instantiated")
        instance = Singleton._instances.get(cls)
        if instance is None:
            instance = cls()
            Singleton._instances[cls] = instance
        return cast(T, instance)
