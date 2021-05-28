"""Script to maintain an image on the canvas."""

import dataclasses
import logging
import typing as t

import numpy as np
from PIL import Image

from . import core

# logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("[%(levelname)s] %(name)s - %(asctime)s - %(message)s")
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
        protecting = True
        while protecting:
            for job in jobs:
                # Flatten names to avoid changing the rest of the code
                image = job.image
                origin = job.origin
                # Get current canvas
                sketch = self.painter.sketch()
                # Iterate image until we find a different pixel
                for y in range(image.shape[0]):
                    for x in range(image.shape[1]):
                        # Check if there is any opacity
                        if image[y, x, 3] != 0:
                            # todo consider blending when not total opacity
                            goal = core.Colour.from_triple(image[y, x, :3])
                            # Map image coords onto canvas, depending on anchors
                            # todo eventually restore anchor capability?
                            canvasX = origin[0] + x
                            canvasY = origin[1] + y
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
                                self.painter.paint(canvasX, canvasY, goal)
                                # Refresh canvas since paint can block for a while
                                sketch = self.painter.sketch()


def main() -> None:
    """Main function"""

    with open(".env", "r") as env:
        # Assume env only contains token=TOKEN
        token = env.read().strip()[len("token=") :]

    painter = core.Painter(token, warmup=120)
    protector = Protector(painter)

    # Prepare jobs
    jobs = []
    with Image.open("python.png") as image:
        jobs.append(Job(np.asarray(image), (139, 0)))
    with Image.open("soft-edged-wilson.png") as image:
        jobs.append(Job(np.asarray(image), (160, 16)))
    with Image.open("yert.png") as image:
        jobs.append(Job(np.asarray(image), (0, 30)))
    # with Image.open("canada.png") as image:
    #     jobs.append(Job(np.asarray(image), (50, 91)))

    # # Load image with PIL, convert to RGB so painter can handle it
    # with Image.open("python.png") as image:
    #     rgb = image.convert("RGBA")
    #     # Start protection
    #     protector.activate((20, 0), rgb, xEdge=True)

    # with Image.open("canada.png") as image:
    #     rgb = image.convert("RGBA")
    #     # Start protection
    #     protector.activate((50, 91), rgb)

    # protector.activate(jobs)

    sketch = painter.sketch()
    print(sketch[0, 0])


if __name__ == "__main__":
    main()
