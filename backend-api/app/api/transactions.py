from fastapi import APIRouter, Depends, HTTPException, Query, Header
import hashlib
import json
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..core.security import get_current_user
from ..schemas import SyncOperationResult, SyncRequest, SyncResponse, Transaction, TransactionOut
from ..models import Transaction as TransactionModel, Merchant as MerchantModel

router = APIRouter()


def request_fingerprint(payload: Transaction) -> str:
    encoded = json.dumps(payload.model_dump(mode="json", exclude={"user_id"}), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def transaction_output(txn: TransactionModel) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        merchant_id=txn.merchant_id,
        user_id=txn.user_id,
        amount=txn.amount,
        currency=txn.currency,
        type=txn.type,
        timestamp=txn.timestamp,
    )


async def persist_transaction(
    payload: Transaction,
    user_id: str,
    db: AsyncSession,
    idempotency_key: str | None = None,
):
    payload_hash = request_fingerprint(payload)
    if idempotency_key:
        if not 8 <= len(idempotency_key) <= 128:
            raise HTTPException(status_code=422, detail="Invalid Idempotency-Key length")
        existing_result = await db.execute(select(TransactionModel).where(TransactionModel.idempotency_key == idempotency_key))
        existing = existing_result.scalar_one_or_none()
        if existing:
            if existing.user_id != user_id or existing.idempotency_hash != payload_hash:
                raise HTTPException(status_code=409, detail="Idempotency key already used")
            return existing, True

    merchant_result = await db.execute(select(MerchantModel).where(MerchantModel.id == payload.merchant_id))
    merchant = merchant_result.scalars().first()
    if not merchant:
        merchant = MerchantModel(id=payload.merchant_id, name=f"merchant-{payload.merchant_id}")
        db.add(merchant)
        await db.flush()

    txn = TransactionModel(
        merchant_id=payload.merchant_id,
        user_id=user_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        type=payload.type,
        idempotency_key=idempotency_key,
        idempotency_hash=payload_hash if idempotency_key else None,
    )
    db.add(txn)
    await db.flush()
    return txn, False


@router.post("/transactions", response_model=TransactionOut, status_code=201)
async def create_transaction(payload: Transaction, db: AsyncSession = Depends(get_db), user=Depends(get_current_user), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    user_id = user.get("username")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    txn, _ = await persist_transaction(payload, user_id, db, idempotency_key)
    await db.commit()
    await db.refresh(txn)
    return transaction_output(txn)


@router.post("/transactions/sync", response_model=SyncResponse)
async def sync_transactions(request: SyncRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    results = []
    for operation in request.operations:
        try:
            payload = Transaction(**operation.model_dump(exclude={"idempotency_key"}))
            txn, already_processed = await persist_transaction(payload, user_id, db, operation.idempotency_key)
            await db.commit()
            await db.refresh(txn)
            results.append(SyncOperationResult(
                idempotency_key=operation.idempotency_key,
                status="already_processed" if already_processed else "accepted",
                transaction=transaction_output(txn),
            ))
        except HTTPException as exc:
            await db.rollback()
            results.append(SyncOperationResult(idempotency_key=operation.idempotency_key, status="rejected", error=exc.detail))
        except Exception:
            await db.rollback()
            results.append(SyncOperationResult(idempotency_key=operation.idempotency_key, status="rejected", error="operation could not be processed"))
    return SyncResponse(results=results)


@router.get("/transactions/merchant/{merchant_id}", response_model=List[TransactionOut])
async def list_transactions_for_merchant(merchant_id: int, limit: int = Query(50, ge=1, le=100), db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    q = select(TransactionModel).where(TransactionModel.merchant_id == merchant_id, TransactionModel.user_id == user_id).order_by(TransactionModel.timestamp.desc()).limit(limit)
    res = await db.execute(q)
    txns = res.scalars().all()
    return [transaction_output(t) for t in txns]
