import os
import time
from datetime import datetime

from dotenv import load_dotenv

import save_connections


load_dotenv()


POLL_SECONDS = int(
    os.getenv(
        "GMAIL_POLL_SECONDS",
        "45"
    )
)


def run_once():

    print()
    print("=" * 60)

    print(
        "Checking Gmail:",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    print("=" * 60)

    try:

        save_connections.main()

    except Exception as e:

        print()
        print("Worker cycle failed:")

        print(
            type(e).__name__,
            str(e)
        )


def main():

    print("=" * 60)
    print("LinkedIn AI Assistant Worker")
    print("=" * 60)

    print(
        f"Gmail polling interval: "
        f"{POLL_SECONDS} seconds"
    )

    print(
        "Press Ctrl+C to stop."
    )

    while True:

        run_once()

        print()
        print(
            f"Next Gmail check in "
            f"{POLL_SECONDS} seconds..."
        )

        time.sleep(
            POLL_SECONDS
        )


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print()
        print(
            "LinkedIn AI Assistant stopped."
        )