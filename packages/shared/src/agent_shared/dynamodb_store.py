from datetime import datetime, timezone
from typing import Iterable

import boto3
from boto3.dynamodb.conditions import Key

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

class DynamoDBStore(BaseStore):
    """Minimal LangGraph store backed by DynamoDB.

    Supports get/put/search against an exact namespace only - no semantic search,
    no true namespace-prefix search across depths, no list_namespaces. That's
    enough for nodes that read/write per-user records under a fixed namespace
    like (user_id, "emails"); it is not a general-purpose Store implementation.

    Requires a table with partition key "namespace" (String) and sort key
    "item_key" (String).
    """

    def __init__(self, table_name: str, region_name: str):
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def _get(self, op: GetOp):
        response = self._table.get_item(
            Key={"namespace": "#".join(op.namespace), "item_key": op.key}
        )
        item = response.get("Item")
        if not item:
            return None
        return Item(
            value=item["value"],
            key=item["item_key"],
            namespace=tuple(item["namespace"].split("#")),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )

    def _put(self, op: PutOp):
        namespace = "#".join(op.namespace)
        if op.value is None:
            self._table.delete_item(Key={"namespace": namespace, "item_key": op.key})
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._table.put_item(Item={
            "namespace": namespace,
            "item_key": op.key,
            "value": op.value,
            "created_at": now,
            "updated_at": now,
        })
        return None

    def _search(self, op: SearchOp):
        namespace = "#".join(op.namespace_prefix)
        response = self._table.query(
            KeyConditionExpression=Key("namespace").eq(namespace),
            ScanIndexForward=False,
        )
        items = response.get("Items", [])
        if op.filter:
            items = [
                i for i in items
                if all(i["value"].get(k) == v for k, v in op.filter.items())
            ]
        items = items[op.offset: op.offset + op.limit]
        return [
            SearchItem(
                namespace=tuple(i["namespace"].split("#")),
                key=i["item_key"],
                value=i["value"],
                created_at=i["created_at"],
                updated_at=i["updated_at"],
            )
            for i in items
        ]

    def batch(self, ops: Iterable[Op]) -> list:
        results = []
        for op in ops:
            if isinstance(op, GetOp):
                results.append(self._get(op))
            elif isinstance(op, PutOp):
                results.append(self._put(op))
            elif isinstance(op, SearchOp):
                results.append(self._search(op))
            elif isinstance(op, ListNamespacesOp):
                raise NotImplementedError("DynamoDBStore does not support list_namespaces")
            else:
                raise NotImplementedError(f"Unsupported op: {type(op)}")
        return results

    async def abatch(self, ops: Iterable[Op]) -> list:
        return self.batch(ops)
