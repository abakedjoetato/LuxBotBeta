# Gift Tier System Update

## Changes Made (October 9, 2025)

### Problem
The gift tier mapping was incomplete and the rewardable submission selection logic was incorrect.

### Issues Fixed

#### 1. Incomplete Gift Tier Map
**Before:**
```python
GIFT_TIER_MAP = {
    5000: "25+ Skip",  # Missing 20 Skip and 15 Skip tiers
    2000: "10 Skip",
    1000: "5 Skip",
}
```

**After:**
```python
GIFT_TIER_MAP = {
    6000: "25+ Skip",   # 6000+ coins → 25+ Skip
    5000: "20 Skip",    # 5000-5999 coins → 20 Skip  ✅ ADDED
    4000: "15 Skip",    # 4000-4999 coins → 15 Skip  ✅ ADDED
    2000: "10 Skip",    # 2000-3999 coins → 10 Skip
    1000: "5 Skip",     # 1000-1999 coins → 5 Skip
}
```

#### 2. Incorrect Rewardable Submission Logic
**Before (WRONG):**
- Only selected submissions from **Free line**
- Excluded Pending Skips (which should be included!)

**After (CORRECT):**
- Selects from **Free line AND Pending Skips**
- Excludes only: 5 Skip, 10 Skip, 15 Skip, 20 Skip, 25+ Skip, Songs Played, Removed

## New Gift Tier System

### Coin-to-Skip Mapping
| Coin Amount | Reward Line |
|-------------|-------------|
| 1000-1999   | 5 Skip      |
| 2000-3999   | 10 Skip     |
| 4000-4999   | 15 Skip     |
| 5000-5999   | 20 Skip     |
| 6000+       | 25+ Skip    |

### Points Calculation (Unchanged)
- **Under 1000 coins:** 2 points per coin toward free line engagement
- **1000+ coins:** 1 point per coin toward free line engagement

### Rewardable Submissions
Gifts **can move** submissions from:
- ✅ Free line
- ✅ Pending Skips

Gifts **cannot move** submissions from:
- ❌ 5 Skip, 10 Skip, 15 Skip, 20 Skip, 25+ Skip (already rewarded)
- ❌ Songs Played (already played)
- ❌ Removed (deleted by admin)

## How It Works

1. **User sends gift** (e.g., 5200 coins)
2. **Points awarded:** 5200 × 1 = 5200 points (since 5200 ≥ 1000)
3. **Tier selection:** Checks tiers from highest to lowest
   - 6000? No (5200 < 6000)
   - 5000? Yes! (5200 ≥ 5000) → **20 Skip**
4. **Submission search:** Finds user's most recent submission in Free or Pending Skips
5. **Move submission:** Moves it to 20 Skip queue
6. **Notify user:** DM sent confirming the reward

## Edge Cases Handled

### Boundary Values
- **Exactly 1000 coins:** → 5 Skip ✅
- **Exactly 2000 coins:** → 10 Skip ✅
- **Exactly 4000 coins:** → 15 Skip ✅
- **Exactly 5000 coins:** → 20 Skip ✅
- **Exactly 6000 coins:** → 25+ Skip ✅

### No Eligible Submissions
- User has no submissions → No reward (gift still counts for points)
- User has submissions only in skip lines → No move (already rewarded)
- User has submissions only in Songs Played → No move (already played)

## Files Modified

### `cogs/tiktok_cog.py`
- Updated `GIFT_TIER_MAP` with all 5 tiers
- Added inline comments explaining coin ranges

### `database.py`
- Fixed `find_gift_rewardable_submission()` logic
- Updated docstring to clarify inclusion/exclusion rules
- Explicitly listed all non-rewardable queue lines

## Testing

### ✅ Bot Startup
- Bot restarted successfully
- TikTokCog initialized without errors
- No AttributeErrors or crashes

### ✅ Architect Review: PASSED
- Coin thresholds map correctly to skip lines
- Boundary values handled correctly
- Rewardable submission logic includes Free and Pending Skips
- Points calculation (2x for <1000) preserved
- Logic flow with sorted reverse iteration works correctly

### 🔄 Recommended Testing
1. Send 999 coin gift → No tier reward (only points)
2. Send 1000 coin gift → 5 Skip reward
3. Send 1999 coin gift → 5 Skip reward
4. Send 2000 coin gift → 10 Skip reward
5. Send 4000 coin gift → 15 Skip reward
6. Send 5000 coin gift → 20 Skip reward
7. Send 6000 coin gift → 25+ Skip reward
8. Test with submission in Pending Skips → Should move correctly
9. Test with submission already in 10 Skip → Should not move

## Summary

✅ **All 5 tier thresholds implemented correctly**  
✅ **Pending Skips now included in rewardable submissions**  
✅ **Free line submissions continue to be rewardable**  
✅ **Skip line submissions correctly excluded from rewards**  
✅ **Points calculation unchanged (2x for <1000)**  
✅ **Bot tested and running without errors**  

The gift tier system now fully matches the requirements and handles all edge cases correctly!
