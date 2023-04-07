import sqlite3
import os
from ipywidgets import Button
from ipywidgets import Textarea
from ipywidgets import RadioButtons
from ipywidgets import Checkbox
from ipywidgets import IntText
from ipywidgets import GridspecLayout
import csv
from lamonpy import Lamon
import re
from rpy2.robjects import r

lamon = Lamon()
word_pattern = re.compile("[a-z]+")


class Settings:
    _root_dir = None
    _widgets = []

    def __str__(self):
        return self.name + "_" + str(hex(self))

    def __hash__(self):
        return hash((self._settings))

    def get_group_field(self):
        group = self.widgets["grp"].value

        if group == "Paragraph":
            return "par_id"
        else:
            return group.lower()

    def _load_settings(self):
        ...
        # store values in self._settings
        settings = []
        for key, widget in self.widgets.items():
            try:
                settings.append((key, widget.value))
            except AttributeError:
                pass
        self._settings = tuple(settings)

    def _record_settings(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

            with open(
                os.path.join(self.data_dir, "setting.txt"), "x", encoding="utf8"
            ) as settings_writer:
                for setting in self._settings:
                    settings_writer.write(str(setting) + "\n")

    def update_settings(self):
        self._load_settings()

        self.data_dir = os.path.join(self._root_dir, str(self))

        if not os.path.exists(self.data_dir):
            self._record_settings()

            self._use_updated_settings()


class Corpus(Settings):
    def __init__(self, root_data_path, database_name):
        self.db = os.path.join(root_data_path, database_name)
        self.name = "corpus"

        if not os.path.exists(root_data_path):
            raise FileNotFoundError(
                f"Could not find: {root_data_path}",
            )

        elif not os.path.exists(self.db):
            raise FileNotFoundError(
                f"Could not find a database named: {database_name} '\
                f'in dir {root_data_path}"  # noqa: E501
            )

        self._root_dir = os.path.join(root_data_path, "corpora")

        # set stopwords set.

        self._use_updated_settings = self._export_corpus

        with open("stopwords_latin.txt", "r", encoding="utf8") as f:
            self.sw = set(row for row in f if not row.startswith("#") and row != "")

        self.widgets = {
            "grp": RadioButtons(
                options=["Paragraph", "Title", "Author"],
                description="Grouping",
                value="Paragraph",
            ),
            "lem": Checkbox(value=True, description="Lemmatize"),
            "chars": IntText(value=1, description="Minimum token length"),
            "save": Button(
                description="Save settings",
                icon="check",
                tooltip="Save settings and generate new corpus.",
                disables=False,
                value=False,
            ),
            "sw": Textarea(value="\n".join(self.sw), description="StopWords", rows=20),
        }
        self.widgets["save"].on_click(self.button_func())

        self.gui = GridspecLayout(4, 4)
        self.gui[:, 1] = self.widgets["sw"]
        self.gui[0, 0] = self.widgets["grp"]
        self.gui[1, 0] = self.widgets["lem"]
        self.gui[2, 0] = self.widgets["chars"]
        self.gui[3, 0] = self.widgets["save"]

        self._load_settings()

        self.get_options_from_db()

        # todo: add stm installation
        r("library(stm)")

    def get_options_from_db(self):
        with sqlite3.connect(self.db, uri=True) as db:
            self.authors = [
                (author[0], "auth_" + author[0].split("-")[0])
                for author in db.execute(
                    "select distinct author from corpus_raw"
                ).fetchall()
                if author[0] is not None
            ]
            self.works = [
                (work[0], "wrk_" + work[0].replace(" ", "_"))
                for work in db.execute(
                    "select distinct title from corpus_raw"
                ).fetchall()
                if work[0] is not None
            ]

    def button_func(self):
        def start_update(*args):
            self.update_settings()

            r(f"data <- read.csv('{self.corpus_file_path}')")
            r(
                """
                processed <- textProcessor(
                    data$d,
                    metadata=data,
                    removestopwords=FALSE,
                    removepunctuation=FALSE,
                    stem=FALSE,
                    )
                """
            )
            r(
                """
                out <- prepDocuments(
                    processed$documents,
                    processed$vocab,
                    processed$meta,
                    lower.thresh=1
                    )
                """
            )
            r(
                """
                docs <- data$documents
                vocab <- out$vocab
                meta <- out$meta

                """
            )

        return start_update

    def _load_settings(self):
        self.sw = set(_ for _ in self.widgets["sw"].value.split("\n"))
        self.widgets["sw"].value = "\n".join(sorted(self.sw))

        super()._load_settings()

    def _export_corpus(self, force=False):
        ...
        # first check if it exists
        self.corpus_file_path = os.path.join(self.data_dir, "corpus.csv")
        if not force and not os.path.exists(self.corpus_file_path):
            with sqlite3.connect(self.db, uri=True) as db:
                query = self.construct_query()

                cur = db.cursor()

                cur.execute(query)

                columns = [column[0] for column in cur.description]

                results = [dict(zip(columns, row)) for row in cur.fetchall()]

            with open(self.corpus_file_path, "x", encoding="utf8") as f:
                writer = csv.DictWriter(f, fieldnames=columns)

                writer.writeheader()
                for line in results:
                    # preprocess each line, and skip empty lines
                    writer.writerow(line)

    def construct_query(self):
        # todo: construct query from settings

        query = 'select group_concat(document, " ") as document, '
        for col, pairings in [("author", self.authors), ("title", self.works)]:
            for value, header in pairings:
                query += f'CASE WHEN {col} == "{value}" THEN 1 ELSE 0 END AS {header}, '

        query += "row from corpus_raw group by " + self.get_group_field()

        return query

    @staticmethod
    def lemmatize(text, sw):
        lemmas = [tag[2] for tag in lamon.tag(text)[0][1]]
        lemmas = [_ for _ in lemmas if _ not in sw and "[" not in _]
        return " ".join(lemmas)


class STM(Settings):
    def __init__(self, corpus):
        self.corpus = corpus
        self.name = "stm"

        self.widgets = {
            "k": IntText(value=7, description="Number of topics"),
            "i": IntText(value=5, description="Maximum number of iterations"),
            "auth": Checkbox(value=True, description="By author"),
            "work": Checkbox(value=True, description="By work"),
            "btn": Button(
                description="Fit stm",
                icon="check",
                tooltip="Save settings and generate new corpus.",
                disables=False,
                value=False,
            ),
        }
        self.widgets["btn"].on_click(self.button_func())

        self.gui = GridspecLayout(3, 2)
        self.gui[0, 0] = self.widgets["k"]
        self.gui[1, 0] = self.widgets["i"]
        self.gui[0, 1] = self.widgets["auth"]
        self.gui[1, 1] = self.widgets["work"]
        self.gui[2, :] = self.widgets["btn"]

    def build_prevanence_formula(self):
        variables = []
        if self.widgets["auth"]:
            variables += [col for val, col in self.corpus.authors]

        if self.widgets["work"]:
            variables += [col for val, col in self.corpus.works]

        if len(variables) > 0:
            return ", prevalence =~ " + "+".join(variables)
        else:
            return ""

    def button_func(self):
        self.update_settings()

        def fit_stm(*args):
            prevalence = self.build_prevanence_formula()

            r(
                f"""
                stm_fit <- stm(
                documents = out$documents,
                vocab = out$vocab,
                K={self.widgets['k'].value},
                max.em.its = {self.widgets['i'].value},
                data = meta,
                init.type = "Spectral"
                {prevalence}
                )
                """
            )

        return fit_stm

    def plot_stm(self, plot_type, **kwargs):
        plot_path = os.path.join(
            self.data_dir, (str(plot_type) + str(kwargs) + ".pnt").replace(" ", "_")
        )

        if not os.path.exists(plot_path):
            r(
                f"""
                dev.off()
                jpeg(file={plot_path})
                plot(stm_fit, type="{plot_type}")
                dev.off()
                """
            )
        return plot_path
