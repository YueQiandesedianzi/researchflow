import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def series_forecast(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["predictions"].path)
    time_col = params["time_column"]
    for col in (time_col, "y_true", "y_pred"):
        if col not in df.columns:
            raise ValueError(f"预测表缺少 {col!r} 列（model.predict 请用 index_columns 携带时间列）")
    df = df.assign(**{time_col: pd.to_datetime(df[time_col])})
    df = df.sort_values(time_col, kind="stable")
    if len(df) > params["max_points"]:
        df = df.iloc[: params["max_points"]]
    fig, ax = plt.subplots(figsize=(9, 4), dpi=150)
    ax.plot(df[time_col], df["y_true"], label="y_true", lw=1.2)
    ax.plot(df[time_col], df["y_pred"], label="y_pred", lw=1.0, alpha=0.8)
    ax.legend()
    ax.set_title(params.get("title", "Forecast vs actual"))
    ax.set_xlabel(time_col)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_dir / "forecast.png")
    plt.close(fig)
    log(f"forecast.png（{len(df)} 点）")
    return {"figure": "forecast.png"}
