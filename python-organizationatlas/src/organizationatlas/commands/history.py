"""Organization history command."""

from organizationatlas.helpers import get_organization_history

from ._base import make_command

history_command = make_command(
    get_organization_history,
    api_command="get_organization_history",
    arg_name="code",
    description="Get historized organization values (use --code organization_code)",
    with_readable=True,
)
