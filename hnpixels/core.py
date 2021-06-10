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
        """Returns the colour of a given pixel.

        Negative indices are subtracted from width and height respectively.
        """
        # We take a (x, y) key and access the content in row major order
        x, y = key
        # Convert negative indices to positive via length - i
        if x < 0:
            x = self.width + x
        if y < 0:
            y = self.height + y
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

    # TODO clean up this method. should we be passing limit?
    # what should we be passing?
    # should requests-period be taken into account?
    def unlock(
        self, remaining: int, limit: int, reset: float
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
            logger.info("Sleeping for %.2f seconds", self.guard_time - current)
            time.sleep(self.guard_time - current)


class RatelimitError(requests.HTTPError):
    """Specific HTTPError that indicates the error was due to ratelimiting.

    Therefore it will be most likely safe to retry later.
    """


TMR: int = requests.codes.too_many_requests  # pylint: disable=no-member


@dataclasses.dataclass(init=False)
class Endpoint:
    """Manages an endpoint.

    Tracks whether the endpoint can be communicated with,
    rate limits, etc.
    """

    method: str
    url: str
    headers: t.Optional[t.Mapping[str, str]] = None

    def __init__(
        self, method: str, url: str, *, headers: t.Optional[t.Mapping[str, str]] = None
    ) -> None:
        """Constructs an Endpoint.

        Requests will be made to the given URL,
        and the headers given will be used as default headers,
        with keys overridden by headers provided to the call.
        """
        self.url = url
        self.method = method
        self.headers = headers

        self.ratelimiter = Ratelimiter()
        # denotes whether the endpoint has actually been successfully queried,
        # for ratelimit headers, etc
        self._active = False

    def update_ratelimiter(self, headers: t.Mapping[str, str]) -> None:
        """Updates (unlock) the given ratelimiter using the following headers:

        remaining: requests-remaining
        limit: requests-limit
        reset: requests-reset
        """
        logger.debug(headers)
        try:
            self.ratelimiter.unlock(
                remaining=int(headers["requests-remaining"]),
                limit=int(headers["requests-limit"]),
                reset=float(headers["requests-reset"]),
            )
        except KeyError:
            try:
                self.ratelimiter.unlock(
                    remaining=0, limit=0, reset=float(headers["cooldown-reset"])
                )
            except KeyError:
                try:
                    self.ratelimiter.unlock(
                        remaining=0, limit=0, reset=float(headers["retry-after"])
                    )
                except KeyError as error:
                    raise KeyError(
                        f"No ratelimit headers found in {headers}"
                    ) from error

    def activate(self) -> None:
        """Performs a HEAD request to load ratelimit information"""
        response = requests.head(self.url, headers=self.headers)
        if response.ok:
            self.update_ratelimiter(response.headers)
        # 429 isnt a fatal error here
        # To Many Requests (i.e. ratelimited) code
        elif response.status_code == TMR:
            self.update_ratelimiter(response.headers)
            raise RatelimitError("Received 429", response=response)
        else:
            response.raise_for_status()

    def request(self, **kwargs: t.Any) -> requests.Response:
        """Fetches the endpoint, passing along kwargs to requests.request.

        Uses default headers unionized with provided headers if provided.
        """

        if not self._active:
            try:
                self.activate()
            except RatelimitError:
                # Try again, should succeed
                try:
                    self.activate()
                except requests.HTTPError as error:
                    raise requests.HTTPError(
                        f"Failed to access endpoint {self}"
                    ) from error
            except requests.HTTPError as error:
                # reraise
                raise requests.HTTPError(f"Failed to access endpoint {self}") from error
            # One of the above activates should have succeded
            # to reach this point
            self._active = True

        # Start with an empty dict and attempt to update it with default and provided headers
        headers: t.MutableMapping[str, str] = {}
        if self.headers:
            headers.update(self.headers)
        try:
            headers.update(kwargs["headers"])
        except KeyError:
            pass

        # Attempt to ensure ratelimit compliance
        self.ratelimiter.lock()
        response = requests.request(
            # If headers is empty we dont both passing it at all
            self.method,
            self.url,
            headers=headers if headers else None,
            **kwargs,
        )

        if response.ok:
            # Maintain ratelimiter
            self.update_ratelimiter(response.headers)
            # Succesful response can be returned
            return response
        # Update ratelimiter, allows calling code to catch and recall
        elif response.status_code == TMR:
            self.update_ratelimiter(response.headers)
            raise RatelimitError("Received 429", response=response)
        # might be dumb but raising custom httperror since raise_for_status
        # isnt guaranteed too from a typecheck perspective
        else:
            raise requests.HTTPError("Bad response from endpoint", response=response)


# TODO List:
# more logging (for all behaviour/requests not just setting)
# deeper consideration of http error codes
#   429 is already handled, but sometimes stray 500 etc can be received.
#   although potentially those should be handled by client code,
#   since the library may not be able to assume that failing a call is okay
# switch to async (sizeable task)
class Painter:
    """Client object for interacting with the Pixels API.

    All API methods may block to obey ratelimits.
    """

    def __init__(self, token: str) -> None:
        """Constructs a new Painter using the given token.

        A token can be obtained from https://pixels.pythondiscord.com/authorize.

        Optionally provide a warmup to wait before interacting with the API.
        """
        self.headers = {"Authorization": f"Bearer {token}"}
        self._api = "https://pixels.pythondiscord.com"

        self._get_pixel_endpoint = Endpoint(
            "GET", self.endpoint("/get_pixel"), headers=self.headers
        )
        self._get_pixels_endpoint = Endpoint(
            "GET", self.endpoint("/get_pixels"), headers=self.headers
        )
        self._set_pixel_endpoint = Endpoint(
            "POST", self.endpoint("/set_pixel"), headers=self.headers
        )

    def endpoint(self, name: str) -> str:
        """Returns the URL of appending an endpoint name to the API.

        E.g. if the API is https://pixels.pythondiscord.com,
        endpoint("/set_pixel") returns "https://pixels.pythondiscord.com/set_pixel"
        """
        return self._api + name

    def colour(self, x: int, y: int) -> Colour:
        """Returns the colour at the specified position."""
        response = self._get_pixel_endpoint.request(params={"x": x, "y": y})
        # Transform to Colour object
        return Colour.from_hex(response.json()["rgb"])
        # return response.json()["rgb"]

    def paint(self, x: int, y: int, colour: Colour, *, check: bool = True) -> None:
        """Sets the colour of a pixel at the specified position.

        If `check` is true, the method will call .colour before and after
        waiting to short-circuit as soon as possible if the pixel is already
        the correct colour, and avoid wasting set pixel requests.

        May block for a significant period to obey ratelimits.
        """
        # TODO restore checking get_pixel after ratelimit sleeping
        # since sleep can be long (~120s) and the pixel may have changed
        try:
            # only check the colour if required (achieved via short circuit)
            if check and self.colour(x, y) == colour:
                logger.info(
                    "pixel at x=%s,y=%s is already the correct color %s",
                    x,
                    y,
                    colour.hex(),
                )
                # return since we dont need to paint over
                return
        except requests.HTTPError:
            # other than logging, we can just continue
            logger.debug("pixel at x=%s,y=%s has an unknown color.", x, y)

        # Make request
        response = self._set_pixel_endpoint.request(
            json={"x": x, "y": y, "rgb": colour.hex()},
        )

        try:
            logger.info(response.json()["message"])
        except KeyError:
            logger.info("Strange response from /set_pixel: %s", response.content)

    # TODO turn this into an Endpoint using method?
    # bit different with lack of ratelimits
    def size(self) -> t.Tuple[int, int]:
        """Returns the size of the canvas."""
        response = requests.get(self.endpoint("/get_size"), headers=self.headers)
        response.raise_for_status()
        return (response.json()["width"], response.json()["height"])

    def sketch(self) -> Sketch:
        """Returns the current state of the canvas."""
        response = self._get_pixels_endpoint.request()
        return Sketch(response.content, *self.size())
