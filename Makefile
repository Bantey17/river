cython:
	python setup.py build_ext --inplace --force

execute-notebooks:
	jupyter nbconvert --execute --to notebook --inplace docs/*/*.ipynb --ExecutePreprocessor.timeout=-1

render-notebooks:
	jupyter nbconvert --to markdown docs/getting-started.ipynb
	jupyter nbconvert --to markdown docs/user-guide/*.ipynb --output-dir docs/user-guide
	jupyter nbconvert --to markdown docs/examples/*.ipynb --output-dir docs/examples

doc: render-notebooks
	python docs/scripts/index.py
	#python docs/scripts/linkify.py
	mkdocs build

livedoc: doc
	mkdocs serve --dirtyreload
