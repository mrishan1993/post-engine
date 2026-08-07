from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContentFeature, KnowledgeGraphEdge, KnowledgeGraphNode, RawContent


def upsert_node(
    session: Session, node_type: str, label: str, properties: dict | None = None
) -> KnowledgeGraphNode:
    existing = session.scalar(
        select(KnowledgeGraphNode).where(
            KnowledgeGraphNode.node_type == node_type,
            KnowledgeGraphNode.label == label,
        )
    )
    if existing:
        if properties:
            existing.properties = {**(existing.properties or {}), **properties}
        return existing
    node = KnowledgeGraphNode(node_type=node_type, label=label, properties=properties or {})
    session.add(node)
    session.flush()
    return node


def link(
    session: Session,
    from_node: KnowledgeGraphNode,
    to_node: KnowledgeGraphNode,
    relation: str,
    weight: float = 1.0,
) -> KnowledgeGraphEdge:
    edge = KnowledgeGraphEdge(
        from_node_id=from_node.id,
        to_node_id=to_node.id,
        relation=relation,
        weight=weight,
    )
    session.add(edge)
    return edge


def build_graph_from_features(
    session: Session,
    pairs: list[tuple[RawContent, ContentFeature]],
    *,
    vertical_slug: str | None = None,
) -> int:
    """Store relationships: topic → emotion → format → audience (+ vertical)."""
    edges = 0
    for raw, feat in pairs:
        emotion = (feat.emotion or {}).get("dominant") or "unknown"
        story = (feat.story_arc or {}).get("pattern") or "unknown"
        topic_label = (raw.title or "untitled")[:80]
        topic = upsert_node(session, "topic", topic_label, {"source": raw.source})
        emo = upsert_node(session, "emotion", emotion)
        fmt = upsert_node(session, "format", feat.format or story)
        aud = upsert_node(session, "audience", feat.audience or "general")
        hook_type = (feat.hook or {}).get("hook_type") or "unknown"
        hook = upsert_node(session, "hook", hook_type)

        link(session, topic, emo, "evokes")
        link(session, emo, fmt, "expressed_as")
        link(session, fmt, aud, "targets")
        link(session, topic, hook, "opens_with")
        edges += 4

        if vertical_slug:
            vert = upsert_node(session, "vertical", vertical_slug)
            link(session, topic, vert, "fits")
            edges += 1
    session.flush()
    return edges
