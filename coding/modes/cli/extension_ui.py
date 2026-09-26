from coding.extensions.types import ExtensionUIContext


class CliExtensionUI(ExtensionUIContext):
    async def select(self, title: str, options: list[str]) -> str | None:
        print(title, flush=True)

        for idx, opt in enumerate(options, start=1):
            print(f" {idx}. {opt}", flush=True)

        try:
            choice = input(f"Select [1-{len(options)}]: ").strip()
            choice = choice.strip()

            if not choice:
                return

            if choice.isdigit():
                num = int(choice)

                if 1 <= num <= len(options):
                    return options[num - 1]

            return
        except (KeyboardInterrupt, EOFError):
            return

    def notify(self, message: str, level: str = "info") -> None:
        print(f"[{level}] {message}", flush=True)
