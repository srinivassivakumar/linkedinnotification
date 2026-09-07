import subprocess
import sys
import time


def start_process(script_name):
    return subprocess.Popen(
        [
            sys.executable,
            "-u",
            script_name
        ],
        stderr=subprocess.STDOUT
    )


def stop_process(process):
    if process.poll() is None:
        process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    print("=" * 60, flush=True)
    print("Starting LinkedIn AI Assistant", flush=True)
    print("=" * 60, flush=True)

    print(flush=True)
    print("Starting Gmail worker...", flush=True)
    gmail_worker = start_process("worker.py")

    print("Starting Telegram callback worker...", flush=True)
    telegram_worker = start_process("telegram_callback_worker.py")

    print(flush=True)
    print("Both workers are running.", flush=True)
    print("Press Ctrl+C to stop everything.", flush=True)
    print(flush=True)

    try:
        while True:
            if gmail_worker.poll() is not None:
                print(
                    "Gmail worker stopped unexpectedly "
                    f"with exit code {gmail_worker.returncode}.",
                    flush=True
                )
                break

            if telegram_worker.poll() is not None:
                print(
                    "Telegram callback worker stopped unexpectedly "
                    f"with exit code {telegram_worker.returncode}.",
                    flush=True
                )
                break

            time.sleep(2)

    except KeyboardInterrupt:
        print(flush=True)
        print("Stopping LinkedIn AI Assistant...", flush=True)

    finally:
        stop_process(gmail_worker)
        stop_process(telegram_worker)

        print("All workers stopped.", flush=True)


if __name__ == "__main__":
    main()
