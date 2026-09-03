import subprocess
import sys
import time


def start_process(script_name):
    return subprocess.Popen(
        [
            sys.executable,
            script_name
        ]
    )


def main():

    print("=" * 60)
    print("Starting LinkedIn AI Assistant")
    print("=" * 60)

    print()
    print("Starting Gmail worker...")
    gmail_worker = start_process(
        "worker.py"
    )

    print("Starting Telegram callback worker...")
    telegram_worker = start_process(
        "telegram_callback_worker.py"
    )

    print()
    print("Both workers are running.")
    print("Press Ctrl+C to stop everything.")
    print()

    try:

        while True:

            # If either worker stops unexpectedly,
            # report it and stop the launcher.

            if gmail_worker.poll() is not None:
                print(
                    "Gmail worker stopped unexpectedly."
                )
                break

            if telegram_worker.poll() is not None:
                print(
                    "Telegram callback worker stopped unexpectedly."
                )
                break

            time.sleep(2)

    except KeyboardInterrupt:

        print()
        print("Stopping LinkedIn AI Assistant...")

    finally:

        if gmail_worker.poll() is None:
            gmail_worker.terminate()

        if telegram_worker.poll() is None:
            telegram_worker.terminate()

        gmail_worker.wait()
        telegram_worker.wait()

        print("All workers stopped.")


if __name__ == "__main__":
    main()