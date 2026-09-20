"""Testes dos gráficos dos notebooks de previsão: cores por método e a figura do quadro."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.analytics_ai.demand_plots import COLORS, comparison_chart, method_color  # noqa: E402


def test_method_color_by_kind():
    assert method_color("MM12 × índice") == COLORS[4]
    assert method_color("Régua final") == COLORS[1]
    assert method_color("Vencedor da validação") == COLORS[3]
    assert method_color("Linear 4: + produto nos outros locais") == COLORS[0]


def test_comparison_chart_draws_one_bar_per_method_in_both_panels():
    table = pd.DataFrame(
        {"Erro por categoria no local (%)": [36.4, 11.9, 12.6], "Viés (%)": [-8.1, -2.8, -7.7]},
        index=["MM12", "Régua final", "Linear 4: + tudo"],
    )
    fig = comparison_chart(table, "Teste")
    try:
        assert len(fig.axes) == 2
        assert all(len(ax.patches) == 3 for ax in fig.axes)
        assert fig._suptitle.get_text() == "Teste"
    finally:
        plt.close(fig)
