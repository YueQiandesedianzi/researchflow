import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def residuals(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["predictions"].path)
    y_true = df["y_true"].to_numpy(dtype=float)
    y_pred = df["y_pred"].to_numpy(dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    res = y_true[mask] - y_pred[mask]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4), dpi=150)
    ax1.hist(res, bins=40)
    ax1.axvline(0, color="k", lw=0.8)
    ax1.set_xlabel("residual (y_true - y_pred)")
    ax1.set_ylabel("count")
    ax1.set_title("Residual histogram")
    ax2.scatter(y_pred[mask], res, s=8, alpha=0.5, edgecolors="none")
    ax2.axhline(0, color="k", lw=0.8, ls="--")
    ax2.set_xlabel("y_pred")
    ax2.set_ylabel("residual")
    ax2.set_title("Residual vs prediction")
    fig.suptitle(params.get("title", "Residuals"))
    fig.tight_layout()
    fig.savefig(out_dir / "residuals.png")
    plt.close(fig)
    log(f"residuals.png（{len(res)} 点）")
    return {"figure": "residuals.png"}
