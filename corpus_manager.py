import sqlite3
import os
from ipywidgets import Button
from ipywidgets import Textarea
from ipywidgets import RadioButtons
from ipywidgets import Checkbox
from ipywidgets import IntText
from ipywidgets import GridspecLayout
from ipywidgets import Image
from ipywidgets import VBox
import csv
import re
import logging
from rpy2.robjects import r
from rpy2.rinterface import embedded

# from lamonpy import Lamon
# lamon = Lamon()

word_pattern = re.compile("[a-z]+")


class Settings:
    _root_dir = None
    _widgets = []
    buttons = []

    def _use_updated_settings(self):
        pass

    def __hash__(self):
        return hash((self._settings))

    def __str__(self):
        return self.name + "_" + str(hex(hash(self)))

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
                if key == "display":
                    continue
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

        if os.path.exists(self.data_dir):
            return False
        else:
            logging.debug("Has has changed, recording settings etc.")
            self._record_settings()

            self._use_updated_settings()
            return True

    def button_wrapper(self, func):
        def inner(button):
            self.deactivate_buttons()
            try:
                func(button)
            except Exception as e:
                print(e)
                button.icon = "X"
                button.button_style = "danger"

            self.activate_buttons()
            button.icon = "check"
            button.button_style = "success"

        return inner

    def deactivate_buttons(self):
        for button in self.buttons:
            button.icon = "hourglass"
            button.button_style = "warning"
            button.disable = True

    def activate_buttons(self):
        for button in self.buttons:
            button.icon = "ellipsis"
            button.button_style = ""
            button.disable = False


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

        # todo: add download for stopwords.
        with open("stopwords_latin.txt", "r", encoding="utf8") as f:
            self.sw = set(row for row in f if not row.startswith("#") and row != "")

        self.widgets = {
            "grp": RadioButtons(
                options=["Paragraph", "Title", "Author"],
                description="Grouping",
                value="Author",
            ),
            "lem": Checkbox(value=True, description="Lemmatize"),
            "chars": IntText(value=1, description="Minimum token length"),
            "btn": Button(
                description="Save settings",
                icon="ellipsis",
                tooltip="Save settings and generate new corpus.",
                disables=False,
                value=False,
            ),
            "sw": Textarea(value="\n".join(self.sw), description="StopWords", rows=20),
        }
        self.widgets["btn"].on_click(self.button_func())

        self.gui = GridspecLayout(4, 4)
        self.gui[:, 1] = self.widgets["sw"]
        self.gui[0, 0] = self.widgets["grp"]
        self.gui[1, 0] = self.widgets["lem"]
        self.gui[2, 0] = self.widgets["chars"]
        self.gui[3, 0] = self.widgets["btn"]

        self._load_settings()

        self.get_options_from_db()

        # todo: add stm installation
        r("library(stm)")

        self.update_settings()
        self.load_r_data()
        self.stm = STM(self)

        self.buttons.append(self.widgets["btn"])

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
        @self.button_wrapper
        def start_update(button):
            if not self.update_settings():
                return None

            self.load_r_data()

        return start_update

    def load_r_data(self):
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
                    line["document"] = self.cleaner(line["document"], self.sw)
                    # preprocess each line, and skip empty lines
                    writer.writerow(line)

    def construct_query(self):
        # todo: construct query from settings

        text_col = "par_lem" if self._settings[1][1] else "par_raw"

        query = f'select group_concat({text_col}, " ") as document, '
        for col, pairings in [("author", self.authors), ("title", self.works)]:
            for value, header in pairings:
                query += f'CASE WHEN {col} == "{value}" THEN 1 ELSE 0 END AS {header}, '

        query += "row from corpus_raw group by " + self.get_group_field()

        return query

    @staticmethod
    def cleaner(text, sw):
        text = word_pattern.findall(text)
        if sw is not None:
            text = [_ for _ in text if _ not in sw and "[" not in _]
        return " ".join(text)


class STM(Settings):
    def __init__(self, corpus):
        self.corpus = corpus
        self.name = "stm"
        self._root_dir = self.corpus.data_dir
        self.corpus = corpus

        self.widgets = {
            "k": IntText(
                value=3, description="Number of topics", tooltip="Number of topics"
            ),
            "i": IntText(
                value=1,
                description="Maximum number of iterations",
                tooltip="Maximum number of iterations",
            ),
            "auth": Checkbox(value=True, description="By author"),
            "work": Checkbox(value=True, description="By work"),
            "btn": Button(
                description="Fit stm",
                icon="ellipsis",
                tooltip="Save settings and generate new corpus.",
                disable=False,
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

        self.update_settings()
        self.plotter = Plotter(self)

        self.update_settings()

        self.buttons.append(self.widgets["btn"])

    def update_settings(self):
        super().update_settings()

        if hasattr(self, "plotter"):
            self.plotter.widgets["topics"] = [
                Checkbox(value=True, description=f"Topic {k+1}")
                for k in range(self.widgets["k"].value)
            ]
            self.plotter.widgets["topic_list"].items = self.plotter.widgets["topics"]
            self.plotter.gui[:, -1] = VBox(self.plotter.widgets["topics"])

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

        @self.button_wrapper
        def fit_stm(button):
            self.corpus.deactivate_buttons()

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

            self.corpus.activate_buttons()
            button.icon = "check"
            button.button_style = "success"

        return fit_stm


class Plotter(Settings):
    def __init__(self, stm):
        self.name = "plot"
        self._root_dir = stm.data_dir
        self.stm = stm

        self.widgets = {
            "type": RadioButtons(
                value="hist",
                options=["hist", "perspectives", "labels"],
                descripton="Plot type",
            ),
            "display": Image(),
            "btn": Button(
                description="Visualize",
                tooltip="Make and show plot",
                disable=False,
                value=False,
                icon="ellipsis",
            ),
            "topic_list": VBox()
            # todo: add optional arguments
        }
        self.gui = GridspecLayout(5, 5)
        self.gui[0, 0] = self.widgets["type"]
        self.gui[0, -2] = self.widgets["btn"]
        self.gui[:, -1] = self.widgets["topic_list"]
        self.gui[1:, 1:-1] = self.widgets["display"]

        self.widgets["btn"].on_click(self.button_func())

        self.update_settings()

        self.buttons.append(self.widgets["btn"])

    def button_func(self):
        @self.button_wrapper
        def button_plotter(button):
            self.plot_stm(plot_type=self.widgets["type"].value)

        return button_plotter

    def plot_stm(self, plot_type):
        try:
            r("stm_fit")
        except embedded.RRunntimeError:
            print("missing stm model")
            return None

        first = 2 if plot_type == "perspectives" else self.stm._settings[0][1]

        topics = ", ".join(
            [
                cbox.description.split(" ")[-1]
                for cbox in self.widgets["topics"]
                if cbox.value
            ][:first]
        )
        plot_path = os.path.join(
            self.data_dir,
            (str(self) + str(plot_type) + str(topics) + ".jpeg").replace(" ", "_"),
        )

        if not os.path.exists(plot_path):
            r(
                f"""
                jpeg(file="{plot_path}")
                plot(stm_fit, type="{plot_type}", topics = c({topics}))
                dev.off()
                """
            )
        self.widgets["display"].value = open(plot_path, "rb").read()