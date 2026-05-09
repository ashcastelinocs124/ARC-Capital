"""Pluggable post sources for the figure-deviation engine.

Each tracked figure has one or more sources (audio, x_api, sonar_tweet) that
emit `FigurePost` objects. All sources implement `FigurePostSource` so the
shared scoring/baseline/gate machinery downstream is source-agnostic.
"""
