import asyncio

from pyzeebe import ZeebeWorker, create_insecure_channel

from ai_factory.config import ZEEBE_ADDRESS, check_environment


async def run_worker() -> None:
    # Import po sprawdzeniu środowiska, żeby brak klucza dał czytelny komunikat
    from ai_factory.handlers import router

    channel = create_insecure_channel(grpc_address=ZEEBE_ADDRESS)
    worker = ZeebeWorker(channel)
    worker.include_router(router)

    print(f"AI Factory gotowe. Nasłuchuję na Camunda 8 (Zeebe) pod {ZEEBE_ADDRESS}...")
    await worker.work()


def main() -> None:
    check_environment()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
