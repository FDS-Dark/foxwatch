"""Plot the saved v2 cross-validation confusion matrix without retraining."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    directory = Path(__file__).with_name("artifacts")
    report = json.loads((directory / "logistic_regression_v2.json").read_text(encoding="utf-8"))
    matrix = np.asarray(report["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(7.5, 6.5), layout="constrained")
    ax.imshow(matrix, cmap="Blues", vmin=0, vmax=matrix.max())
    labels = ["No bloom (0)", "Bloom (1)"]
    ax.set_xticks([0, 1], labels)
    ax.set_yticks([0, 1], labels)
    ax.set_xlabel("Predicted label", fontsize=12, labelpad=12)
    ax.set_ylabel("Actual label", fontsize=12, labelpad=12)
    ax.set_title("Logistic regression v2\nConfusion matrix", fontsize=18, pad=20)
    names = [["True negatives", "False positives"], ["False negatives", "True positives"]]
    for row in range(2):
        for column in range(2):
            count = matrix[row, column]
            color = "white" if count > matrix.max() / 2 else "#142d40"
            ax.text(column, row - 0.07, str(count), ha="center", va="center", fontsize=30, weight="bold", color=color)
            ax.text(column, row + 0.16, names[row][column], ha="center", va="center", fontsize=11, color=color)
    ax.tick_params(length=0, pad=10)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.suptitle("5-fold stratified cross-validation · Threshold 0.5 · 366 observations", fontsize=10)
    for extension in ("png", "svg"):
        path = directory / f"logistic_regression_v2_confusion_matrix.{extension}"
        fig.savefig(path, dpi=200, facecolor="white")
        print(path)
    plt.close(fig)


if __name__ == "__main__":
    main()
