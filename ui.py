"""Figma's PaperFit desktop design, adapted to native Streamlit controls."""
from html import escape
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent


def install():
    st.html(f'<style>{(ROOT / "static" / "paperfit.css").read_text()}</style>')


def text(value, kind='body'):
    st.html(f'<p class="pf-{kind}">{escape(str(value))}</p>')


def badge_html(label, tone='neutral'):
    tone = tone if tone in ('neutral', 'positive', 'warning', 'danger') else 'neutral'
    return f'<span class="pf-badge {tone}">{escape(str(label))}</span>'


def badges(items, note=''):
    st.html('<div class="pf-badges">' + ''.join(badge_html(label,tone) for label,tone in items)
            + (f'<span class="pf-meta">{escape(note)}</span>' if note else '') + '</div>')


def page_header(section, title, subtitle, saved=False):
    st.html(f'<div class="pf-breadcrumb"><span>工作区 / {escape(section)}</span>'
            + badge_html('已保存到本机' if saved else '本机工作区', 'positive' if saved else 'neutral') + '</div>')
    with st.container(key='page_heading', gap=None):
        st.title(title)
        text(subtitle, 'subtitle')


def stats(results, priorities):
    st.html('<div class="pf-stats">' + ''.join(
        f'<div class="pf-stat"><span class="pf-stat-number">{sum(r["priority"] == p for r in results)}</span>'
        f'<span class="pf-meta">{escape(p)}</span></div>' for p in priorities) + '</div>')


def quote(location, value):
    st.html(f'<div class="pf-quote"><div class="pf-meta">引文已定位 · {escape(location)}</div>'
            f'<p>{escape(value)}</p></div>')


def actions(key=None):
    return st.container(horizontal=True, gap='small', vertical_alignment='center', key=key)


def card(key):
    return st.container(border=True, key=f'card_{key}', gap='small')
