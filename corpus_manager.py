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
from ipywidgets import Label
import csv
import re
import logging
from rpy2.robjects import r
from rpy2.rinterface import embedded
import hashlib

# from lamonpy import Lamon
# lamon = Lamon()

word_pattern = re.compile("[a-z]+", re.IGNORECASE)


class Settings:
    _root_dir = None
    _widgets = []
    buttons = []

    def _use_updated_settings(self):
        pass

    def __hash__(self):
        try:
            return int(hashlib.md5(self.settings_str.encode("utf-8")).hexdigest(), 16)
        except AttributeError:
            self._load_settings()
            return hash(self)

    def __str__(self):
        return self.name + "_" + str(hex(hash(self)))

    def get_group_field(self):
        group = self.widgets["grp"].value

        if group == "Paragraph":
            return "par_id"
        elif "letter" in group:
            return "title"
        elif group == "Work":
            return "source"
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
        self.settings_str = "\n".join(str(setting) for setting in self._settings)

    def _record_settings(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        settings_path = os.path.join(self.data_dir, "setting.txt")

        if not os.path.exists(settings_path):
            with open(settings_path, "x", encoding="utf8") as settings_writer:
                settings_writer.write(self.settings_str)
        else:
            with open(settings_path, "r", encoding="utf8") as settings_reader:
                settings_str = settings_reader.read()

            if self.settings_str != settings_str:
                raise ValueError("Read and calculated settings differ")

    def update_settings(self):
        self._load_settings()

        self.data_dir = os.path.join(self._root_dir, str(self))

        if os.path.exists(self.data_dir):
            return False
        else:
            logging.debug("Has has changed, recording settings etc.")
            os.makedirs(self.data_dir, exist_ok=True)
            self._record_settings()

            self._use_updated_settings()
            return True

    def button_wrapper(self, func):
        def inner(button):
            self.update_settings()
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

            self.update_settings()

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
            self.sw_base = set(
                row.strip() for row in f if not row.startswith("#") and row != ""
            ) | {"unk", "num"}
            self.sw = self.sw_base

        self.widgets = {
            "grp": RadioButtons(
                options=["Paragraph", "Work", "Author", "Work w/ letters separated"],
                description="Grouping",
                value="Work",
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
            "user_sw": Textarea(value="", description="UserStopwords", rows=20),
        }
        self.widgets["btn"].on_click(self.button_func())

        self.gui = GridspecLayout(4, 4)
        self.gui[:, 1] = self.widgets["sw"]
        self.gui[:, 2] = self.widgets["user_sw"]
        self.gui[0, 0] = self.widgets["grp"]
        self.gui[1, 0] = self.widgets["lem"]
        self.gui[2, 0] = self.widgets["chars"]
        self.gui[3, 0] = self.widgets["btn"]

        self.get_options_from_db()

        for package in ("stm", "igraph", "tm"):
            r(
                "if('"
                + package
                + f"' %in% rownames(installed.packages()) == FALSE) "
                + "{install.packages('"
                + package
                + "')}"
            )
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
                (work[0].replace(" ", "_"), "wrk_" + work[0].replace(" ", "_"))
                for work in db.execute(
                    "select distinct source from corpus_raw"
                ).fetchall()
                if work[0] is not None
            ]

    def button_func(self):
        @self.button_wrapper
        def start_update(button):
            self.load_r_data()

        return start_update

    def load_r_data(self):
        r_data_path = os.path.join(self.data_dir, "corpus.RData")

        if not os.path.exists(r_data_path):
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
            r(f'save(data, processed, out, docs, vocab, meta, file="{r_data_path}")')
        else:
            print("Corpus data found, loading.")
            r(f'load("{r_data_path}")')

    def _load_settings(self):
        add = []
        remove = []
        for sw in self.widgets["user_sw"].value.split("\n"):
            sw = sw.strip()
            if sw.startswith("-"):
                remove.append(sw[1:])
            else:
                add.append(sw)

        self.sw = (self.sw_base | set(add)) - set(remove)
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
        text_col = "par_lem" if self._settings[1][1] else "par_raw"

        query = f'select group_concat({text_col}, " ") as document, '
        for col, pairings in [("author", self.authors), ("source", self.works)]:
            for value, header in pairings:
                header = header.replace("-", "_")
                query += f'CASE WHEN {col} == "{value}" THEN 1 ELSE 0 END AS {header}, '

        query += "letter, row from corpus_raw group by " + self.get_group_field()

        return query

    @staticmethod
    def cleaner(text, sw):
        text = word_pattern.findall(text.lower())
        if sw is not None:
            text = [_ for _ in text if _ not in sw and "[" not in _]
        return " ".join(text)

    def update_settings(self):
        super().update_settings()
        self._export_corpus()
        if hasattr(self, "stm"):
            self.stm.update_settings()
            self.stm.plotter.update_settings()


class STM(Settings):
    def __init__(self, corpus):
        self.corpus = corpus
        self.name = "stm"
        self.corpus = corpus
        self._root_dir = self.corpus.data_dir

        self.widgets = {
            "k": IntText(
                value=3, description="Number of topics", tooltip="Number of topics"
            ),
            "i": IntText(
                value=1,
                description="Maximum number of iterations",
                tooltip="Maximum number of iterations",
            ),
            "auth": Checkbox(value=False, description="By author"),
            "work": Checkbox(value=True, description="By work"),
            "letters": Checkbox(value=False, description="Letters"),
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
        self.gui[2, 1] = self.widgets["letters"]
        self.gui[2, 0] = self.widgets["btn"]

        self.update_settings()
        self.plotter = Plotter(self)

        self.update_settings()

        self.buttons.append(self.widgets["btn"])

    def update_settings(self):
        self._root_dir = self.corpus.data_dir
        super().update_settings()

        if hasattr(self, "plotter"):
            for checkbox in self.plotter.widgets["topics"]:
                del checkbox

            self.plotter.widgets["topics"] = [
                Checkbox(value=False, description=f"Topic {k+1}")
                for k in range(self.widgets["k"].value)
            ]
            self.plotter.widgets["topic_list"].items = self.plotter.widgets["topics"]
            self.plotter.gui[:, -1] = VBox(self.plotter.widgets["topics"])

    def build_prevalence_formula(self):
        variables = []
        if self.widgets["auth"].value:
            variables += [col for val, col in self.corpus.authors]

        if self.widgets["work"].value:
            variables += [col for val, col in self.corpus.works]

        if self.widgets["letters"].value:
            variables += ["letter"]

        if len(variables) > 0:
            return ", prevalence =~ " + "+".join(variables)
        else:
            return ""

    def button_func(self):
        @self.button_wrapper
        def fit_stm(button):
            self.update_settings()

            self.stm_path = os.path.join(self.data_dir, "stm.RData")
            if os.path.exists(self.stm_path):
                print("STM model found, loading")
                r(f'load("{self.stm_path}")')

            else:
                prevalence = self.build_prevalence_formula()

                r(
                    f"""
                    stm_fit <- stm(
                    documents = out$documents,
                    vocab = out$vocab,
                    K={self.widgets['k'].value},
                    max.em.its = {self.widgets['i'].value},
                    data = meta,
                    init.type = "Spectral",
                    gamma.prior = "L1"
                    {prevalence}
                    )
                    """
                )

                r(f'save(stm_fit, file="{self.stm_path}")')

            button.icon = "check"
            button.button_style = "success"

        return fit_stm


class Plotter(Settings):
    def __init__(self, stm):
        self.name = "plot"
        self.stm = stm
        self._root_dir = self.stm.data_dir

        self.widgets = {
            "type": RadioButtons(
                value="default",
                options=["default", "hist", "perspectives", "labels", "topicCorr"],
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
            "topic_list": VBox(),
            "topics": [Checkbox()],
            "label": Label(value=self._root_dir),
        }
        self.gui = GridspecLayout(6, 5)
        self.gui[-1, 0:-1] = self.widgets["label"]
        self.gui[0, 0] = self.widgets["type"]
        self.gui[0, -2] = self.widgets["btn"]
        self.gui[1:, -1] = self.widgets["topic_list"]
        self.gui[2:-1, 0:-1] = self.widgets["display"]

        self.widgets["btn"].on_click(self.button_func())

        self.update_settings()

        self.buttons.append(self.widgets["btn"])

    def update_settings(self):
        self._root_dir = self.stm.data_dir
        super().update_settings()
        self.widgets["label"].value = str(self.data_dir)

    def button_func(self):
        @self.button_wrapper
        def button_plotter(button):
            self.plot_stm(plot_type=self.widgets["type"].value)

        return button_plotter

    def plot_stm(self, plot_type):
        if plot_type == "topicCorr":
            self.topiccorr()
        elif plot_type == "default":
            self.plain_plot()
        else:
            self.basic_plot(plot_type)

    def selected_topics_as_str(self, plot_type):
        first = 2 if plot_type == "perspectives" else self.stm._settings[0][1]
        return ", ".join(
            [
                cbox.description.split(" ")[-1]
                for cbox in self.widgets["topics"]
                if cbox.value
            ][:first]
        )

    def basic_plot(self, plot_type):
        try:
            r("stm_fit")
        except embedded.RRunntimeError:
            print("missing stm model")
            return None

        topics = self.selected_topics_as_str(plot_type)
        plot_path = os.path.join(
            self.data_dir,
            (str(self) + str(plot_type) + str(topics) + ".jpeg").replace(" ", "_"),
        )

        if not os.path.exists(plot_path):
            r(
                f"""
                jpeg(file="{plot_path}")
                plot(stm_fit, type="{plot_type}", topics = c({topics}),
                text.cex = 0.75,
                )
                dev.off()
                """
            )
        self.widgets["display"].value = open(plot_path, "rb").read()

    def topiccorr(self):
        plot_path = os.path.join(self.data_dir, "topicCorr.jpg")
        if not os.path.exists(plot_path):
            r(
                f"""
        cormat <- topicCorr(stm_fit)
        jpeg("{plot_path}", width=3.25, height=3.25, res=1200, units="in")
        plot(cormat)
        dev.off()
        """
            )
        self.widgets["display"].value = open(plot_path, "rb").read()

    def plain_plot(self):
        topics = self.selected_topics_as_str("default")

        plot_path = os.path.join(self.data_dir, "default.jpg")
        if not os.path.exists(plot_path):
            r(
                f"""
        jpeg("{plot_path}")
        plot(stm_fit, topics = c({topics}))
        dev.off()
        """
            )
        self.widgets["display"].value = open(plot_path, "rb").read()


if __name__ == "__main__":
    corpus = Corpus(root_data_path="data", database_name="corpus.sqlite3")
    stm = corpus.stm

    stm.widgets["btn"].click()

    plotter = stm.plotter
