---
name: Log band cosine
overview: Replace histogram intersection of linear band shares with cosine similarity of mean-centered log band energies, and keep the paper sources in the scorer comments.
todos:
  - id: log-bands
    content: Replace sum-to-1 band shares with floored, mean-centered log band energies, citing Seyerlehner et al. DAFx 2008 eq. 3
    status: completed
  - id: cosine
    content: Score frames with cosine similarity instead of histogram intersection, citing Foote SPIE 1997, and point DTW at it
    status: completed
  - id: check
    content: Score the clips against themselves, a quiet copy, and broadband noise; self and quiet stay near 100, noise stays under 70
    status: completed
isProject: false
---

# Log-band cosine score

The 70% line stays. The frame feature in [app/score.py](app/score.py) changes. An exact copy still scores 100 because cosine of a vector with itself is 1. A microphone take stops losing half its score to linear noise mass.

No new markdown file. Copy the citations below into the docstrings of the two functions that implement them. No spectral-flatness gate and no MFCC stack: the existing 8 log-spaced bands, 25 ms frames, 10 ms hop, and 80 ms Sakoe-Chiba band stay.

## Sources

- Klaus Seyerlehner, Gerhard Widmer, and Peter Knees. "Frame Level Audio Similarity — A Codebook Approach." In Proc. of the 11th Int. Conference on Digital Audio Effects (DAFx-08), Espoo, Finland, 1–4 September 2008. https://www.cp.jku.at/research/papers/Seyerlehner_etal_DAFx_2008.pdf
  - Equation 3 converts summed band power to decibels before any comparison: `X(k)dB = 20 log10(X(k))`. This is the frame feature.
  - Equations 6 and 7 show that histogram intersection on two histograms with the same bin sum is half an L1 distance: `1 - Σ min(Ii, Mi) / Σ Mi = (1 / 2n) Σ |Ii - Mi|`. That identity is why linear band shares sit around 25–57 for a real take. Do not keep intersection.
- Jonathan T. Foote. "Content-Based Retrieval of Music and Audio." In Multimedia Storage and Archiving Systems II, Proc. SPIE 3229, pp. 138–147, 1997. Cited by Seyerlehner et al. as reference [10]: compare spectral histograms with Euclidean or cosine distance. This scorer already reports a cosine-shaped percentage and uses `1 - similarity` as the DTW local cost, so the distance is cosine.
- Michael J. Swain and Dana H. Ballard. "Color Indexing." International Journal of Computer Vision, vol. 7, no. 1, pp. 11–32, November 1991. Cited by Seyerlehner et al. as reference [16]. This is the origin of histogram intersection, used there on a bag-of-frames histogram for a whole song after the log step, not on per-frame linear band shares. Cite it in the comment that says what the scorer no longer does.
- Beth Logan and Ariel Salomon. "A Music Similarity Function Based on Signal Analysis." In Proc. IEEE International Conference on Multimedia and Expo (ICME), Tokyo, August 2001. Cited by Seyerlehner et al. as reference [3]. Read and not implemented: their feature is MFCCs. This change stops at log band energies.
- Jürgen Herre, Eric Allamanche, and Oliver Hellmuth. "Robust Matching of Audio Signals Using Spectral Flatness Features." In Proc. IEEE Workshop on Applications of Signal Processing to Audio and Acoustics (WASPAA), pp. 127–130, 2001. https://doi.org/10.1109/aspaa.2001.969559 Read and not implemented: spectral flatness (geometric mean over arithmetic mean) is an MPEG-7 tonality feature. It does not restore the 0–100 scale.

## Frame feature

Replace `_band_distribution` (per-frame sum-to-1) with the log step from Seyerlehner et al. 2008, equation 3, applied to the power bands from `_frame_spectra`:

- A frame whose band sum is below `1e-12` stays all zeros, so silence is still silence.
- Otherwise each band is `20 * log10` of its power, floored at a small fraction of that frame's peak so a dead band is finite instead of `-inf`.
- Subtract the frame mean. A gain is a constant in the log domain, so this is what keeps loudness from creating a match.

The docstring cites Seyerlehner, Widmer, and Knees 2008, equation 3, and the URL above.

## Frame distance

Replace `_band_overlap` with cosine similarity of those centered log vectors, as in Foote 1997 (Seyerlehner et al. 2008, reference [10]). Keep the current silence rule: two zero frames match, one zero frame matches nothing. Clamp a negative cosine to 0 so the reported percentage cannot go below 0.

The docstring cites Foote 1997, and notes that Swain and Ballard 1991 intersection (Seyerlehner et al. 2008, equations 6–7 and reference [16]) is the measure being removed.

`_dtw_similarity` is unchanged apart from calling the renamed cosine and wording the docstring as mean cosine along the path. [config.json](config.json) `threshold_percent` stays 70.

## Check

Run the four clips in `sounds/` through `Scorer`:

- Each clip against itself, and against the same samples at 0.15 gain: both near 100.
- Each clip against broadband noise of the same length: under 70.
- A pure tone against that noise: under 70.

Format [app/score.py](app/score.py) with Black.
