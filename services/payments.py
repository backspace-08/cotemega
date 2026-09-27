import aiohttp

from config import LAVA_API_KEY, LAVA_OFFER_ID
from core.logger import logger
from core.utils import run_db
from db.queries import delete_pending_payment, finalize_payment, get_pending_payment

LAVA_API_URL = "https://gate.lava.top"


async def create_lava_invoice(user_id: int, currency: str, amount: float) -> tuple[str | None, str]:
    payload = {
        "email": f"user_{user_id}@example.com",
        "offerId": LAVA_OFFER_ID,
        "amount": amount,
        "currency": currency,
    }
    headers = {"X-Api-Key": LAVA_API_KEY, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{LAVA_API_URL}/api/v3/invoice", json=payload, headers=headers) as resp:
            if resp.status == 422:
                logger.error(f"Lava API 422: {await resp.text()}")
                return None, "Ошибка создания счёта. Попробуйте позже."
            if resp.status >= 400:
                logger.error(f"Lava API {resp.status}: {await resp.text()}")
                return None, "Ошибка создания счёта. Попробуйте позже."
            data = await resp.json()

    invoice_id = data.get("id")
    payment_url = data.get("paymentUrl")
    if not invoice_id or not payment_url:
        logger.error(f"Lava API unexpected response: {data}")
        return None, "Не удалось получить ссылку на оплату."
    return invoice_id, payment_url


async def process_lava_webhook(data: dict, bot) -> str:
    """Handle a Lava notification. Returns a status; raises on processing errors.

    The pending invoice is persisted in the DB, so a bot restart between the
    payment and the webhook does not lose the payment.
    """
    event_type = data.get("eventType")
    if event_type != "payment.success":
        logger.info(f"Lava webhook skipped: {event_type}")
        return "ignored"

    contract_id = data.get("contractId")
    if not contract_id:
        logger.warning("Lava webhook without contractId")
        return "ignored"

    pending = await run_db(get_pending_payment, contract_id)
    if not pending:
        logger.warning(f"Lava webhook for unknown invoice: {contract_id}")
        return "unknown"

    user_id = int(pending["user_id"])
    shards = int(pending["shards"])
    currency = pending.get("currency", "RUB")
    amount = pending.get("amount", 0)
    operation_id = data.get("operationId") or contract_id

    status = await run_db(
        finalize_payment, operation_id, user_id, amount, shards, f"lava_{contract_id}"
    )
    await run_db(delete_pending_payment, contract_id)

    if status == "ok":
        try:
            await bot.send_message(user_id, f"✅ Оплата получена!\nНачислено 🔮 {shards} осколков.")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Lava payment notify error for {user_id}: {e}")
        logger.info(f"Lava payment processed: user={user_id}, {currency}={amount}, shards={shards}")
    elif status == "duplicate":
        logger.info(f"Lava webhook: duplicate payment {operation_id}, skipped")
    else:
        logger.error(f"Lava webhook: cannot finalize {operation_id} (status={status})")
    return status
