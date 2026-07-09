from bot_core import bot, logger, pending_lava_payments
from bd_workers import plus_shards, mark_payment_processed, is_payment_processed


def process_lava_webhook(data):
    event_type = data.get("eventType")
    if event_type != "payment.success":
        logger.info(f"Lava webhook skipped: {event_type}")
        return

    contract_id = data.get("contractId")
    if not contract_id:
        logger.warning("Lava webhook without contractId")
        return

    pending = pending_lava_payments.pop(contract_id, None)
    if not pending:
        logger.warning(f"Lava webhook for unknown invoice: {contract_id}")
        return

    user_id = pending["user_id"]
    shards = pending["shards"]
    currency = pending.get("currency", "RUB")
    amount = pending.get("amount", 0)
    operation_id = data.get("operationId") or contract_id

    try:
        if is_payment_processed(operation_id):
            logger.info(f"Lava webhook: duplicate payment {operation_id}, skipped")
            return

        if shards > 0:
            plus_shards(user_id, shards)
        mark_payment_processed(operation_id, int(user_id), amount, "shards", shards, f"lava_{contract_id}")
        bot.send_message(
            user_id,
            f"✅ Оплата получена!\nНачислено 🔮 {shards} осколков.",
        )
        logger.info(f"Lava payment processed: user={user_id}, {currency}={amount}, shards={shards}")
    except Exception as e:
        logger.error(f"Lava payment processing error: {e}")
