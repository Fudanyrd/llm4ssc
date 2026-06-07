"""
Draw figures/tables from our artifact (instead of hard-code in paper).
"""

import matplotlib.pyplot as plt
import numpy as np
import bibtexparser
import json, sys, os, subprocess
from typing import Any

THIS_FILE = os.path.join('script', 'draw.py')

"""
Utilities.
"""

def load_json(*paths):
    pth = os.path.join(*paths)
    with open(pth, 'r', encoding='utf-8') as fobj:
        return json.load(fobj)


def plot_trend(years: range, trend_data: dict[str, list[int]], ofile: str):
    """
    [Example graph](https://matplotlib.org/stable/gallery/lines_bars_and_markers/barchart.html#grouped-bar-chart-with-labels)
    """
    x = np.arange(len(years))  # the label locations
    width = 0.20  # the width of the bars
    multiplier = 0

    fig, ax = plt.subplots(layout='constrained')

    legends = list(trend_data.keys())

    for attribute, measurement in trend_data.items():
        offset = width * multiplier
        rects = ax.bar(x + offset, measurement, width, label=attribute.title())
        ax.bar_label(rects, padding=3)
        multiplier += 1
    ax.legend(legends)
    ax.set_xticks(x + 0.3, [str(year) for year in years])
    ax.set_ylabel('# Publications')

    plt.savefig(ofile)
    plt.close()

"""
Build targets management.
"""

class Target():
    __slots__ = ['deps', 'output']

    def __init__(self, dependencies: list[str], output: str):
        self.deps = dependencies
        self.output = output

    def register(self, fobj):
        """
        Write the dependency info in a .d file which Makefile can load.
        """
        fobj.write(f"{self.output}: {' '.join(self.deps)} {THIS_FILE}\n")

    def generate(self):
        raise NotImplementedError("Target is an abstract class")


class PlotTrend(Target):
    __slots__ = ["_k2a", "_a2y", "_after"]
    def __init__(self, dependencies, output, 
                 kind_to_articles: dict, 
                 article_to_year: dict,
                 earliest: int = 2022):
        super().__init__(dependencies, output)
        self._k2a = kind_to_articles
        self._a2y = article_to_year
        self._after = earliest # inclusive

    def generate(self):
        years = range(self._after, max(self._a2y.values()) + 1)
        trend_data = {k: [0] * len(years) for k in self._k2a.keys()}
        for k, articles in self._k2a.items():
            for a in articles:
                y = self._a2y[a]
                if y >= self._after:
                    trend_data[k][y - self._after] += 1
        plot_trend(years, trend_data, self.output)


class PlotPie(Target):
    @staticmethod
    def _weight(value: Any) -> float | int:
        """
        based on the value of object, it determines the weight
        the `key` carries.
        """
        if value is None:
            return 0
        if isinstance(value, list):
            ret = 0
            for v in value: ret += PlotPie._weight(v)
            return ret

        if isinstance(value, dict):
            # likely a smaller concept:
            ret = 0
            for v in value.values(): ret += PlotPie._weight(v)
            return ret

        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, str):
            # possibly an article ID.
            return 1

        raise ValueError(f"Unable to compute weight for type {type(value)}")

    def __init__(self, dependencies, output, 
                 kind_to_articles: dict[str, Any],
                 kind_to_legend: dict | None = None):
        super().__init__(dependencies, output)
        self._k2a = kind_to_articles
        self._k2l = kind_to_legend if kind_to_legend else {k: k.title() for k in kind_to_articles.keys()}

    @staticmethod
    def _index(l : list, v: Any) -> int | None:
        try:
            return l.index(v)
        except ValueError: 
            return None

    def generate(self):
        labels = []
        sizes = []
        for k, v in self._k2a.items():
            w = PlotPie._weight(v)
            legend = self._k2l[k]

            idx = self._index(labels, legend)
            if idx:
                sizes[idx] += w
            else:
                labels.append(self._k2l[k])
                sizes.append(w)
        
        fig, ax = plt.subplots(figsize=(6, 6), layout='constrained')
        # plt.pie(sizes, labels=labels, autopct='%1.1f%%')
        wedges, texts, autotexts = ax.pie(sizes, autopct='%1.1f%%', textprops=dict(color="w"))
        ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        plt.savefig(self.output)
        plt.close()


def drive(targets_to_build: list[Target]):
    depfile = open('main.d', 'w')
    for tgt in targets_to_build:
        tgt.register(depfile)
        tgt.generate()
    depfile.close()


if __name__ == "__main__":
    # generate an amalgamation of bibtex entries.
    subprocess.check_call(['make', 'main.bib'])
    depfile = open('main.d', 'w')

    paper_to_year = {}
    with open('main.bib') as f:
        db = bibtexparser.load(f)
        for entry in db.entries:
            paper_to_year[entry['ID']] = int(entry['year'])
        del db

    rq2_data_file = os.path.join('dataset', 'rq2.json')
    rq2_data = load_json(rq2_data_file)
    tgt = PlotPie([rq2_data_file], os.path.join('logo', 'rq2dist.pdf'), rq2_data)
    tgt.generate(); tgt.register(depfile); del tgt

    # try flatten rq2['vector 1'].
    rq2_vec1_data = rq2_data['vector 1']
    flattened = []
    for v in rq2_vec1_data.values(): flattened += v
    rq2_data['vector 1'] = flattened
    tgt = PlotTrend([rq2_data_file], os.path.join('logo', 'rq2trend.pdf'), rq2_data, paper_to_year)
    tgt.generate(); tgt.register(depfile); del tgt

    depfile.close()
