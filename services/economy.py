from dataclasses import dataclass

from db.queries import get_user_data, update_currency

COST = {"spins": 10, "super_spins": 80}


@dataclass
class ExchangeResult:
    status: str  # ok | insufficient
    target: str
    count: int = 0
    spent: int = 0
    spins: int = 0
    super_spins: int = 0
    shards: int = 0


def exchange(user_id: int, target: str, count: int) -> ExchangeResult:
    """Exchange shards into spins/super_spins. count == 0 means "all"."""
    cost = COST.get(target)
    if cost is None:
        raise ValueError(f"Unknown exchange target: {target}")

    data = get_user_data(user_id)
    if data is None:
        return ExchangeResult(status="insufficient", target=target)

    if count == 0:
        count = data.shards // cost

    if count <= 0 or count * cost > data.shards:
        return ExchangeResult(
            status="insufficient",
            target=target,
            spins=data.spins,
            super_spins=data.super_spins,
            shards=data.shards,
        )

    spent = count * cost
    new_shards = update_currency(user_id, "shards", -spent)
    new_target = update_currency(user_id, target, count)

    data = get_user_data(user_id)
    return ExchangeResult(
        status="ok",
        target=target,
        count=count,
        spent=spent,
        spins=new_target if target == "spins" else data.spins,
        super_spins=new_target if target == "super_spins" else data.super_spins,
        shards=new_shards,
    )
