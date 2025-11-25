import torch
from braindecode.models import EEGNet, ATCNet

MODEL_REGISTRY = {
    "EEGNet": EEGNet,
    "ATCNet": ATCNet,
}


def build_model(cfg: dict, X_train: torch.Tensor, n_outputs: int, device: str = "cpu"):
    model_name = cfg.get("name")
    model_params = cfg.get("params") or {} # cfg.get("params", {})

    model_cls = MODEL_REGISTRY[model_name]

    if X_train.ndim == 3:  # (N, C, T)
        n_chans, n_times = X_train.shape[1], X_train.shape[2]
    elif X_train.ndim == 4:  # (N, 1, C, T)
        n_chans, n_times = X_train.shape[2], X_train.shape[3]
    else:
        raise ValueError(f"错误的shape: {X_train.shape}")

    model = model_cls(
        n_chans=n_chans,
        n_times=n_times,
        n_outputs=n_outputs,
        **model_params,  # 传递可选keyword参数
    )
    return model.to(device)
