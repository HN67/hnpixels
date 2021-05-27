"""Wrapper by HN67 for Python Discord Pixels"""

from __future__ import annotations

import dataclasses
import time
import typing as t

import requests


@dataclasses.dataclass
class Colour:
    """Dataclass containing RGB channels of a 3 byte colour."""

    r: int
    g: int
    b: int

    @classmethod
    def from_hex(cls, hexrep: str) -> Colour:
        """Constructs a Colour object using a 6 digit hex code"""

        if len(hexrep) != 6:
            raise ValueError("Must provide a six digit hex string")

        return cls(int(hexrep[0:2], 16), int(hexrep[2:4], 16), int(hexrep[4:6], 16))

    def hex(self) -> str:
        """Returns the 6 digit hex code representation of this Colour."""
        return "".join(f"{ch:0>2x}" for ch in (self.r, self.g, self.b)).upper()


@dataclasses.dataclass
class Sketch:
    """Dataclass containing canvas state."""

    content: bytes
    width: int
    height: int

    def __getitem__(self, key: t.Tuple[int, int]) -> Colour:
        """Returns the colour of a given pixel."""
        # We take a (x, y) key and access the content in row major order
        x, y = key
        index = x + self.width * y
        return Colour(*self.content[index : index + 3])


class Ratelimiter:
    """Class for managing ratelimits.

    Not guarenteed to be threadsafe at this time.
    """

    def __init__(self, warmup: int = 0) -> None:
        """Constructs a Ratelimiter object, optionally with a warmup wait time."""

        # Time at which lock stops blocking
        self.guard_time = time.time() + warmup

    def unlock(
        self, remaining: int, limit: int, reset: int
    ) -> None:  # pylint: disable=unused-argument
        """Loads the ratelimiter with the specified parameters.

        If remaining is zero, the ratelimiter goes into cooldown for reset amount of seconds.
        """
        if not remaining:
            self.guard_time = time.time() + reset

    def lock(self) -> None:
        """Blocks until internal guard time is passed, at which point it is safe to operate."""
        current = time.time()
        if current < self.guard_time:
            time.sleep(self.guard_time - current)


class Painter:
    """Client object for interacting with the Pixels API.

    All API methods may block to obey ratelimits.
    """

    def __init__(self, token: str) -> None:
        """Constructs a new Painter using the given token.

        A token can be obtained from https://pixels.pythondiscord.com/authorize.
        """
        self.headers = {"Authorization": f"Bearer {token}"}

        self._get_pixel_limiter = Ratelimiter()
        self._set_pixel_limiter = Ratelimiter()
        self._get_canvas_limiter = Ratelimiter()

    def update_ratelimiter(
        self, limiter: Ratelimiter, headers: t.Mapping[str, str]
    ) -> None:
        """Updates (unlock) the given ratelimiter using the following headers:

        remaining: requests-remaining
        limit: requests-limit
        reset: requests-reset
        """
        limiter.unlock(
            remaining=int(headers["requests-remaining"]),
            limit=int(headers["reqeusts-limit"]),
            reset=int(headers["requests-reset"]),
        )

    def pixel(self, x: int, y: int) -> Colour:
        """Returns the colour at the specified position."""
        self._get_pixel_limiter.lock()
        response = requests.get(
            "https://pixels.pythondiscord.com/get_pixel",
            headers=self.headers,
            params={"x": x, "y": y},
        )
        # Throw an informative error, rather than likely an index error on the ["rgb"]
        response.raise_for_status()
        # Load ratelimiter
        self.update_ratelimiter(self._get_pixel_limiter, response.headers)
        # Transform to Colour object
        return Colour.from_hex(response.json()["rgb"])
        # return response.json()["rgb"]

    def paint(self, x: int, y: int, colour: Colour) -> None:
        """Sets the colour of a pixel at the specified position.

        May block for a significant period to obey ratelimits.
        """
        self._set_pixel_limiter.lock()
        response = requests.post(
            "https://pixels.pythondiscord.com/set_pixel",
            headers=self.headers,
            data={"x": x, "y": y, "rgb": colour.hex()},
        )
        response.raise_for_status()
        self.update_ratelimiter(self._set_pixel_limiter, response.headers)
        # verify response?

    def size(self) -> t.Tuple[int, int]:
        """Returns the size of the canvas."""
        response = requests.get(
            "https://pixels.pythondiscord.com/get_size", headers=self.headers
        )
        response.raise_for_status()
        return (response.json()["width"], response.json()["height"])

    def sketch(self) -> Sketch:
        """Returns the current state of the canvas."""
        self._get_canvas_limiter.lock()
        response = requests.get(
            "https://pixels.pythondiscord.com/get_pixels", headers=self.headers
        )
        response.raise_for_status()
        self.update_ratelimiter(self._get_canvas_limiter, response.headers)
        return Sketch(response.content, *self.size())
