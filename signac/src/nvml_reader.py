"""
Reads GPU usage info from CSV file and plots it.
"""
import pandas as pd
import pathlib
from matplotlib import pyplot


def plot_vs_time(grouped, *, ax, col=None, ylabel=None):
    """All plotting is done with time on the x axis,
    this is the base function for that."""
    for uuid, pid in grouped.groups.keys():
        grouped[col].get_group((uuid, pid)).plot(ax=ax, label=f"{uuid}, PID={pid}")

    ax.grid()

    ax.set_ylabel(ylabel)
    ax.set_xlabel("Timestamp")

    return ax


def plot_gpu_usage(grouped, *, ax):
    return plot_vs_time(grouped, col="GPU_Util_%", ylabel="Utilization (%)", ax=ax)


def plot_used_power(grouped, *, ax):
    return plot_vs_time(grouped, col="used_power_W", ylabel="Power (W)", ax=ax)


def plot_used_memory(grouped, *, ax):
    return plot_vs_time(
        grouped, col="used_gpu_memory_MiB", ylabel="MEM usage (MiB)", ax=ax
    )


def main():
    """Main entry point."""
    p = pathlib.Path.cwd() / "nvml.csv"
    df = pd.read_csv(p)

    df["gpu_uuid"] = df["gpu_uuid"].astype("string")
    df["time_stamp"] = pd.to_datetime(df["time_stamp"])
    df.set_index("time_stamp", inplace=True)

    print(df.info(), "\n")
    print(df.describe(), "\n")

    grouped = df.groupby(["gpu_uuid", "pid"])

    fig, axes = pyplot.subplots(figsize=(12, 8), nrows=3, sharex=True)

    for i, (foo, ax) in enumerate(
        zip((plot_gpu_usage, plot_used_power, plot_used_memory), axes.flatten())
    ):
        foo(grouped, ax=ax)
        if i == 0:
            ax.legend()

    fig.savefig("nvml.png", dpi=192)
    pyplot.close(fig)


if __name__ == "__main__":
    main()
