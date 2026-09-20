"""Gráficos compartilhados pelos notebooks de previsão (05 em diante).

Cores fixas por tipo de método e o gráfico de barras que compara o erro por
categoria no local e o viés de cada método do quadro final.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

# azul, laranja, verde, vermelho, cinza
COLORS = ["#2E5C8A", "#E8874C", "#4C9A6A", "#B24C4C", "#9A9A9A"]

ERROR_COLUMN = "Erro por categoria no local (%)"
BIAS_COLUMN = "Viés (%)"


def method_color(name: str) -> str:
    """Cinza = médias móveis, laranja = régua, vermelho = vencedor da validação, azul = o resto."""
    if name.startswith("MM"):
        return COLORS[4]
    if name == "Régua final":
        return COLORS[1]
    if name.startswith("Vencedor"):
        return COLORS[3]
    return COLORS[0]


def comparison_chart(table: pd.DataFrame, title: str) -> Figure:
    """Erro por categoria no local e viés, um método por barra.

    Args:
        table: Quadro de `scorecard_vs_ruler`, um método por linha.
        title: Título da figura.

    Returns:
        A figura; quem chama exibe com `plt.show()`.
    """
    colors = [method_color(name) for name in table.index]
    labels = [name.replace(": ", ":\n") for name in table.index]
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.55 * len(table) + 2.2), sharey=True)
    for ax, column, subtitle in [
        (axes[0], ERROR_COLUMN, "Erro por categoria no local (menor é melhor)"),
        (axes[1], BIAS_COLUMN, "Viés (mais perto de zero é melhor)"),
    ]:
        bars = ax.barh(labels, table[column], color=colors)
        ax.bar_label(bars, fmt="%.1f%%", padding=3)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title(subtitle)
        ax.margins(x=0.15)
    axes[0].invert_yaxis()
    fig.suptitle(title, fontweight="bold")
    fig.tight_layout()
    return fig
