import asyncio


class CancellationSignal:
    def __init__(self):
        self._cancel_event = asyncio.Event()

    def cancel(self):
        # set internal flag to True
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        # Check if internal flag is True or not
        return self._cancel_event.is_set()

    async def wait(self) -> None:
        # For Bash like tool where process can be long running
        # We have one way to do polling at interval and confirm that process is not cancelled
        # But this will waste CPU Cycle
        # We can instead use asyncio.Event on which we can wait without burning cpu cycles
        #
        # Example:
        # process = <bash_process or some long running process>
        # cancel_task = asyncio.create_task(signal.wait())
        # communicate_task = asyncio.create_task(process.communicate())
        #
        # done, _ = await asyncio.wait(
        #     {communicate_task, cancel_task},
        #     timeout=timeout,
        #     return_when=asyncio.FIRST_COMPLETED,
        # )
        #
        # When long running process is running and something trigger cancel then internal flag of Event
        # changes to True and hence .wait completed on it and hence done will contain cancel_task and
        # we can now kill process
        #
        # if cancel_task in done:
        #     process.kill()
        #     await process.wait()
        #     return "Error: Command cancelled by user"
        await self._cancel_event.wait()
