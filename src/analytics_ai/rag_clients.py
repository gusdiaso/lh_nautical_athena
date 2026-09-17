"""Backend-only clients using Databricks unified authentication (CLI or App OAuth)."""
import json

if __package__:
    from .rag_endpoint import RateLimitedChatClient
else:
    from rag_endpoint import RateLimitedChatClient


class WorkspaceIndex:
    """Adapt the authenticated SDK response to retrieve_chunks' existing contract."""
    def __init__(self, workspace, index_name):
        self.workspace = workspace
        self.index_name = index_name

    def similarity_search(self, *, filters=None, query_type="hybrid", **kwargs):
        return self.workspace.vector_search_indexes.query_index(
            index_name=self.index_name, query_type=query_type.upper(),
            filters_json=json.dumps(filters) if filters else None, **kwargs,
        ).as_dict()


def create_clients(index_name, request_interval_seconds=2.0):
    from databricks.sdk import WorkspaceClient

    workspace = WorkspaceClient()
    # SDK supplies refreshed OAuth headers on every request; no static PAT.
    chat = workspace.serving_endpoints.get_open_ai_client(timeout=60, max_retries=0)
    return WorkspaceIndex(workspace, index_name), RateLimitedChatClient(
        chat.chat.completions, request_interval_seconds=request_interval_seconds,
    )
