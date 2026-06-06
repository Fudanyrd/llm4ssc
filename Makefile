TEXFLAGS = --halt-on-error
BIBSRC = dataset/*.bib
TEXSRC = main.tex src/*.tex

main.bib: $(BIBSRC)
	cat $^ > $@

main.pdf: $(TEXSRC) main.bib
	pdflatex $(TEXFLAGS) main.tex
	bibtex main.aux
	pdflatex $(TEXFLAGS) main.tex
	pdflatex $(TEXFLAGS) main.tex

# an archive of source code.
ar.txz: $(TEXSRC) main.bib
	tar cJvf ar.txz main.tex ./src main.bib neurips_2025.sty

.PHONY: clean
clean:
	- rm -f *.aux *.bbl *.blg *.log *.out

UID = $(shell id -u)
GID = $(shell id -g)
PWD = $(shell pwd)

PANDOCFLAGS = --verbose --data-dir=. --citeproc --bibliography=main.bib
PANDOCFLAGS += --resource-path=.  

main.md: $(TEXSRC) main.bib
	docker run --rm \
       --volume "$(PWD):/data" \
       --user $(UID):$(GID) \
       pandoc/minimal:latest-ubuntu \
	   $(PANDOCFLAGS) \
	   main.tex -o main.md

main.docx: $(TEXSRC) main.bib
	docker run --rm \
	   --volume "$(PWD):/data" \
	   --user $(UID):$(GID) \
	   pandoc/minimal:latest-ubuntu \
	   $(PANDOCFLAGS) \
		--number-sections=true \
	   main.tex -o main.docx
