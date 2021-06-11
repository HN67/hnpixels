"""Script to maintain an image on the canvas."""

import dataclasses
import logging
import time
import typing as t

import numpy as np
from PIL import Image

from . import core

# logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s")
)
root_logger.addHandler(handler)

logger = logging.getLogger("protector")

RGBA = np.ndarray


@dataclasses.dataclass
class Job:
    """Job object containing an RGBA 4 channel uint8 ndarray and the origin to be drawn on."""

    image: np.ndarray
    origin: t.Tuple[int, int]


@dataclasses.dataclass
class Protector:
    """Protects an Image using a Painter object."""

    painter: core.Painter

    def activate(self, jobs: t.Sequence[Job]) -> None:
        """Starts an infinite loop protecting the given jobs.

        Checks pixels on the canvas to make sure they are the correct colour,
        repainting them if they are not.
        """

        # Seconds to wait after every protection loop
        wait = 15

        protecting = True
        while protecting:
            for job in jobs:
                # Flatten names to avoid changing the rest of the code
                image = job.image
                imageX, imageY = job.origin
                # Get current canvas
                try:
                    sketch = self.painter.sketch()
                except core.NetworkError as error:
                    logger.error("Failed to get canvas: %s", error)
                else:
                    # Handle negative image coordinates
                    if imageX < 0:
                        imageX = sketch.width + imageX
                    if imageY < 0:
                        imageY = sketch.height + imageY
                    # Iterate image until we find a different pixel
                    for y in range(image.shape[0]):
                        for x in range(image.shape[1]):
                            # Check if there is any opacity
                            if image[y, x, 3] != 0:
                                # todo consider blending when not total opacity
                                goal = core.Colour.from_triple(image[y, x, :3])
                                canvasX = imageX + x
                                canvasY = imageY + y
                                # Check if pixel needs to be fixed
                                current = sketch[canvasX, canvasY]
                                if current != goal:
                                    logger.info(
                                        "Pixel at x=%s,y=%s is different from goal, %s vs %s",
                                        canvasX,
                                        canvasY,
                                        current.hex(),
                                        goal.hex(),
                                    )

                                    # Dont need to use /get_pixel to check live color
                                    # since .paint automatically does that
                                    try:
                                        self.painter.paint(canvasX, canvasY, goal)
                                    except core.NetworkError as error:
                                        logger.error("Failed to set pixel: %s", error)
                                    try:
                                        # Refresh canvas since paint can block for a while
                                        sketch = self.painter.sketch()
                                    except core.NetworkError as error:
                                        logger.error("Failed to get canvas: %s", error)
            # Wait after repairing to avoid fast loop when nothing to repair
            logger.info("Completed full circuit, waiting %s seconds", wait)
            time.sleep(wait)


def main() -> None:
    """Main function"""

    with open(".env", "r") as env:
        # Assume env only contains token=TOKEN
        token = env.read().strip()[len("token=") :]

    painter = core.Painter(token)
    protector = Protector(painter)

    # Prepare jobs
    jobs: t.MutableSequence[Job] = []

    # hidden_message = (
    #     b"Hi! You are banned, sorry. See here for more info: "
    #     b"https://pydis.org/.env | 403 Forbidden          "
    # )
    # rgb_message = np.frombuffer(hidden_message, dtype="uint8").reshape((1, -1, 3))
    # rgba_message = np.dstack(
    #     (rgb_message, np.full(rgb_message.shape[0:2], 255, dtype="uint8"))
    # )
    # jobs.append(Job(rgba_message, (0, 0)))

    images_list = [
        # (("windows_wumpus.png"), (0, 0)),
        # ("mark.png", (111, 131)),
        # ("mark.png", (111, 127)),
        # ("mark.png", (111, 123)),
        # ("python.png", (139, 0)),
        # ("soft-edged-wilson.png", (160, 16)),
        # ("canada.png", (50, 91)),
        # Main canvas
        # ("factorio.png", (255, 119)),
        # ("foxears.png", (90, -8)),
        # ("yert.png", (0, -14)),
        # Emoji canvas
        ("factorio.png", (7, 7))
    ]
    # Transform each image name into an image
    for name, spot in images_list:
        with Image.open(name) as image:
            jobs.append(Job(np.asarray(image.convert("RGBA")), spot))

    protector.activate(jobs)

    # sketch = painter.sketch()
    # print(sketch[0, 1], sketch[1, 0], sketch.content[624:627], sketch.content[3:6])
    # Image.frombytes("RGB", (208, 117), sketch.content).show()


if __name__ == "__main__":
    main()
