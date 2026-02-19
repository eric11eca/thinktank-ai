from langchain.chat_models import BaseChatModel

from src.config import get_app_config
from src.reflection import resolve_class


def create_chat_model(name: str | None = None, thinking_enabled: bool = False, **kwargs) -> BaseChatModel:
    """Create a chat model instance from the config.

    Args:
        name: The name of the model to create. If None, the first model in the config will be used.

    Returns:
        A chat model instance.
    """
    config = get_app_config()
    if name is None:
        name = config.models[0].name
    model_config = config.get_model_config(name)
    if model_config is None:
        raise ValueError(f"Model {name} not found in config") from None
    model_class = resolve_class(model_config.use, BaseChatModel)
    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "supports_thinking",
            "when_thinking_enabled",
            "supports_vision",
        },
    )
    api_key = model_settings_from_config.get("api_key")
    if isinstance(api_key, str):
        if api_key.startswith("$"):
            env_name = api_key[1:]
            raise ValueError(
                f"Model {name} requires environment variable {env_name} to be set. Add it to `.env` or export it before starting the server."
            ) from None
        if not api_key.strip():
            raise ValueError(
                f"Model {name} has an empty api_key. Add it to `.env` or export it before starting the server."
            ) from None
    for field in ("base_url", "api_base"):
        value = model_settings_from_config.get(field)
        if isinstance(value, str) and value.startswith("$"):
            env_name = value[1:]
            raise ValueError(
                f"Model {name} requires environment variable {env_name} to be set. Add it to `.env` or export it before starting the server."
            ) from None
    if thinking_enabled and model_config.when_thinking_enabled is not None:
        if not model_config.supports_thinking:
            raise ValueError(f"Model {name} does not support thinking. Set `supports_thinking` to true in the `config.yaml` to enable thinking.") from None
        model_settings_from_config.update(model_config.when_thinking_enabled)
    model_instance = model_class(**kwargs, **model_settings_from_config)
    return model_instance
