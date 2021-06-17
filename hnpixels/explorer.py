"""Explorer script that searchs for and occupies unclaimed space on the canvas"""

import dataclasses
import json
import logging
import random
import typing as t

import numpy

from . import core

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s")
)
root_logger.addHandler(handler)

logger = logging.getLogger("explorer")


@dataclasses.dataclass()
class History:
    """Denotes whether a pixel has been modified recently.

    Activity is a row-major width*height bytes object.
    """

    # Both are matrices with the first two dimensions
    # matching canvas size.
    # active is 2D with each cell indicating the time since a pixel has been seen modified.
    active: numpy.ndarray
    last: core.Sketch


@dataclasses.dataclass
class Explorer:
    """Explorer class that attempts to spread single colour stakes."""

    painter: core.Painter
    colour: core.Colour

    def load_history(self, path: str) -> History:
        """Loads an activity history array."""
        # Get history structure
        # try:
        #     with open("history.json", "rb") as file:
        #         history_json = json.load(file)
        #         history = History(history_json["active"])
        # except FileNotFoundError:
        #     history = History()

        return self.update_history(None)

    def update_history(self, history: History, sketch: core.Sketch) -> History:
        """Updates a History."""
        for row, col in numpy.ndindex(history.active.shape[:2]):
            if history.last[row, col] != sketch.raw[row, col]:
                history.active[row, col] = 1 # 0?
            else:
                history.active[row, col] += 1
        #     active=numpy.full(
        #         (sketch.height, sketch.height), fill_value=0, dtype=numpy.uint8
        #     ) if not history.active else (history.last == sketch.canvas)
        #     last=sketch,
        # )
        history.last = sketch
        return history
        # Validate history structure
        if not history.active:
            # Construct if it hasnt been
            history.active = 

    def venture(self) -> None:
        """Start exploring the canvas"""
        running = True

        history = self.load_history("history.json")

        while running:

            sketch = self.painter.sketch()

            history = self.update_history(history, sketch)

            # Rules:
            # Find existing <colour> pixels
            #   - Find adjacent black pixels
            #       - expand to one
            #   - If no adjacent black pixels
            #       - spore to random black pixel
            #   - If no black pixels
            #       - check heatmap for unchanged pixels (recently)
            #       - spread to adjacent,
            #       - or spore

            # Find existing colour pixels

            self.painter.paint(
                random.randrange(sketch.width, sketch.height, self.colour)
            )

            # Save history structure
            # TODO


def main() -> None:
    """Entrypoint function"""

    with open(".env", "r") as env:
        # Assume env only contains token=TOKEN
        token = env.read().strip()[len("token=") :]

    painter = core.Painter(token)
    explorer = Explorer(painter, core.Colour.from_hex("FF2E00"))

    explorer.venture()


# Entrypoint block
if __name__ == "__main__":
    main()
