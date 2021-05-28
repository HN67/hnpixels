"""Wrapper by HN67 for Python Discord Pixels"""

from __future__ import annotations

import dataclasses
import logging
import time
import typing as t

import requests

logger = logging.getLogger("hnpixels")
logger.addHandler(logging.NullHandler())


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

        # return cls(int(hexrep[0:2], 16), int(hexrep[2:4], 16), int(hexrep[4:6], 16))
        return cls.from_triple(bytes.fromhex(hexrep))

    def hex(self) -> str:
        """Returns the 6 digit hex code representation of this Colour."""
        return "".join(f"{ch:0>2x}" for ch in (self.r, self.g, self.b)).upper()

    @classmethod
    def from_triple(cls, triple: t.Union[bytes, t.Tuple[int, int, int]]) -> Colour:
        """Constructs a Colour object using a 3 byte bytes string or a Tuple of ints"""

        if len(triple) != 3:
            raise ValueError(
                "Must provide a three byte byte string or three tuple of ints"
            )

        return cls(triple[0], triple[1], triple[2])

    def tuple(self) -> t.Tuple[int, int, int]:
        """Returns the RGB Tuple representation of this colour.

        Should not usually be needed, as Colour should mimic a tuple in most cases.
        """
        return (self.r, self.g, self.b)

    def __getitem__(self, index: int) -> int:
        """Returns a channel of the colour.

        r: 0, g: 1, b: 2
        """
        if index > 2 or index < -3:
            raise IndexError(
                f"Colour only has three channels, index {index} is out of bounds."
            )

        return self.tuple()[index]

    def __iter__(self) -> t.Iterator[int]:
        """Returns an iterator over the r g b."""
        return iter(self.tuple())


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
        # Each pixel is 3 bytes, so we multiple x+width*y by 3
        index = (x + self.width * y) * 3
        return Colour.from_triple(self.content[index : index + 3])


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

    def __init__(self, token: str, warmup: int = 0) -> None:
        """Constructs a new Painter using the given token.

        A token can be obtained from https://pixels.pythondiscord.com/authorize.

        Optionally provide a warmup to wait before interacting with the API.
        """
        self.headers = {"Authorization": f"Bearer {token}"}
        self._api = "https://pixels.pythondiscord.com"

        self._get_pixel_limiter = Ratelimiter(warmup=warmup)
        self._set_pixel_limiter = Ratelimiter(warmup=warmup)
        self._get_canvas_limiter = Ratelimiter(warmup=warmup)

    def endpoint(self, name: str) -> str:
        """Returns the URL of appending an endpoint name to the API.

        E.g. if the API is https://pixels.pythondiscord.com,
        endpoint("/set_pixel") returns "https://pixels.pythondiscord.com/set_pixel"
        """
        return self._api + name

    def update_ratelimiter(
        self, limiter: Ratelimiter, headers: t.Mapping[str, str]
    ) -> None:
        """Updates (unlock) the given ratelimiter using the following headers:

        remaining: requests-remaining
        limit: requests-limit
        reset: requests-reset
        """
        try:
            limiter.unlock(
                remaining=int(headers["requests-remaining"]),
                limit=int(headers["requests-limit"]),
                reset=int(headers["requests-reset"]),
            )
        except KeyError:
            limiter.unlock(remaining=0, limit=0, reset=int(headers["cooldown-reset"]))
        # todo handle 'retry-after' from potential anti-spam
        # also handle ratelimits for arbitrary endpoint (dict?)
        # rather than a static number of limiters

    def colour(self, x: int, y: int) -> Colour:
        """Returns the colour at the specified position."""
        self._get_pixel_limiter.lock()
        response = requests.get(
            self.endpoint("/get_pixel"), headers=self.headers, params={"x": x, "y": y},
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
        # We want to avoid needlessly setting a pixel as much as possible
        # set_pixel ratelimit is extremely low, while other endpoints like get_pixel
        # have much higher limits.
        if self.colour(x, y) == colour:
            logger.info(
                "pixel at x=%s,y=%s is already the correct color %s", x, y, colour.hex()
            )
            return
        # Obey ratelimits
        self._set_pixel_limiter.lock()
        # Waiting on ratelimit can be a while, so we should check the pixel again
        # Potential optimization would be to check how long we waited
        # (make .lock return the time slept?) and only recheck if its long enough (e.g. > 5s)
        if self.colour(x, y) == colour:
            logger.info(
                "pixel at x=%s,y=%s is already the correct color %s", x, y, colour.hex()
            )
            return
        response = requests.post(
            self.endpoint("/set_pixel"),
            headers=self.headers,
            json={"x": x, "y": y, "rgb": colour.hex()},
        )
        try:
            logger.info(response.json()["message"])
        except KeyError:
            logger.info("Strange response from /set_pixel: %s", response.content)
        response.raise_for_status()
        self.update_ratelimiter(self._set_pixel_limiter, response.headers)
        # verify response?

    def size(self) -> t.Tuple[int, int]:
        """Returns the size of the canvas."""
        response = requests.get(self.endpoint("/get_size"), headers=self.headers)
        response.raise_for_status()
        return (response.json()["width"], response.json()["height"])

    def sketch(self) -> Sketch:
        """Returns the current state of the canvas."""
        self._get_canvas_limiter.lock()
        response = requests.get(self.endpoint("/get_pixels"), headers=self.headers)
        response.raise_for_status()
        self.update_ratelimiter(self._get_canvas_limiter, response.headers)
        return Sketch(response.content, *self.size())
