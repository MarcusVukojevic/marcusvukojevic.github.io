---
layout: single
title: "Research"
permalink: /research/
excerpt: "Research on trustworthy language models, model efficiency, one-step graph generation, and graph machine learning."
author_profile: true
---

<div class="mv-page-intro">
  <p class="mv-kicker">Research</p>
  <p class="mv-page-lead">I study how intelligent systems can become more reliable, efficient, and structurally aware without losing the flexibility that makes modern AI useful.</p>
</div>

<div class="mv-research-themes">
  <article>
    <span>01</span>
    <h2>Trustworthy & grounded LLMs</h2>
    <p>My PhD work at the University of Trento investigates ways to detect when a language model leaves the factual manifold. The goal is selective intervention: correct what is unreliable while preserving what already works.</p>
    <div class="mv-tags"><span>Hallucination detection</span><span>Grounding</span><span>Probabilistic circuits</span></div>
  </article>
  <article>
    <span>02</span>
    <h2>Efficient language models</h2>
    <p>I work on post-training compression and pruning: finding which parts of a model are redundant, replacing them with lightweight alternatives, and measuring what capability survives. This includes non-contiguous, submodule-level strategies such as SubFit.</p>
    <div class="mv-tags"><span>Model compression</span><span>Pruning</span><span>Efficient inference</span></div>
  </article>
  <article>
    <span>03</span>
    <h2>One-step graph generation</h2>
    <p>I explore models that produce complete graphs in one neural evaluation. I am interested in how direct generation can support useful and valid outputs across structured domains.</p>
    <div class="mv-tags"><span>Graph generation</span><span>Generative models</span><span>Structured data</span></div>
  </article>
  <article>
    <span>04</span>
    <h2>Graph machine learning</h2>
    <p>RelSC extends graph-regression research beyond common molecular and citation benchmarks. Its homogeneous and multi-relational program graphs make it possible to study how structural representation changes model behaviour.</p>
    <div class="mv-tags"><span>Graph regression</span><span>GNNs</span><span>Program graphs</span></div>
  </article>
</div>

<section class="mv-page-section" aria-labelledby="research-now">
  <p class="mv-kicker">Current work</p>
  <h2 id="research-now">Three threads, one direction.</h2>
  <div class="mv-paper-list">
    <article>
      <time datetime="2026">2026</time>
      <div><h3><a href="https://arxiv.org/abs/2606.02559">From Layers to Submodules: Rethinking Granularity in Replacement-Based LLM Compression</a></h3><p>SubFit compresses LLMs by replacing selected attention and feed-forward submodules with fitted residual bypasses.</p></div>
    </article>
    <article>
      <time datetime="2026">2026</time>
      <div><h3><a href="https://arxiv.org/abs/2605.05953">Hallucination as an Anomaly: Dynamic Intervention via Probabilistic Circuits</a></h3><p>PCNET detects anomalous hidden states and gates corrective decoding only when needed.</p></div>
    </article>
    <article>
      <time datetime="2025">2025-26</time>
      <div><h3><a href="https://arxiv.org/abs/2505.23875">A Benchmark Dataset for Graph Regression with Homogeneous and Multi-Relational Variants</a></h3><p>RelSC provides program-graph benchmarks for homogeneous and heterogeneous graph regression; released on arXiv in 2025 and published in DMLR in 2026.</p></div>
    </article>
  </div>
  <a class="mv-button mv-button--primary" href="/publications/">Publications & links <span aria-hidden="true">→</span></a>
</section>

<section class="mv-page-section mv-note-card" aria-labelledby="collaboration-title">
  <div>
    <p class="mv-kicker">Collaboration</p>
    <h2 id="collaboration-title">Good research gets better in the open.</h2>
  </div>
  <p>I am interested in collaborations around factuality, efficient LLMs, one-step graph generation, and applied AI systems. If your question sits between research and implementation, we will probably have plenty to discuss.</p>
  <a class="mv-text-link" href="mailto:marcusvuk@gmail.com">Start a conversation <span aria-hidden="true">↗</span></a>
</section>
