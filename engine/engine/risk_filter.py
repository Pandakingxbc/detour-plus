def shortlist(screening_results, max_candidates=10):
    risky = [r for r in screening_results if r["is_high_risk"]]
    risky.sort(key=lambda r: r["miss_distance"])
    return risky[:max_candidates]
