"""Script to maintain an image on the canvas."""

import dataclasses
import logging
import typing as t

from PIL import Image

from . import core

logging.basicConfig(level=logging.INFO)


@dataclasses.dataclass
class Protector:
    """Protects an Image using a Painter object."""

    painter: core.Painter

    def activate(self, origin: t.Tuple[int, int], image: Image.Image) -> None:
        """Starts an infinite loop protecting the given image.

        Takes an RBG Image.

        Checks pixels on the canvas to make sure they are the correct colour,
        repainting them if they are not.
        """
        protecting = True
        while protecting:
            # Get current canvas
            sketch = self.painter.sketch()
            # Iterate image until we find a different pixel
            for y in range(image.height):
                for x in range(image.width):
                    # Map image coords onto canvas
                    canvasX = origin[0] + x
                    canvasY = origin[1] + y
                    # Check if pixel needs to be fixed
                    goal = core.Colour.from_triple(image.getpixel((x, y)))
                    current = sketch[canvasX, canvasY]
                    if current != goal:
                        # Refresh current with get_pixel to avoid needless placements
                        # as much as possible
                        current = self.painter.colour(canvasX, canvasY)
                        if current != goal:
                            self.painter.paint(canvasX, canvasY, goal)
                            # Refresh canvas since paint can block for a while
                            sketch = self.painter.sketch()


def main() -> None:
    """Main function"""

    with open(".env", "r") as env:
        # Assume env only contains token=TOKEN
        token = env.read().strip()[len("token=") :]

    painter = core.Painter(token)
    protector = Protector(painter)

    # Load image with PIL, convert to RGB so painter can handle it
    with Image.open("python.png") as image:
        rgb = image.convert("RGB")
        # Start protection
        protector.activate((139, 0), rgb)


if __name__ == "__main__":
    main()
