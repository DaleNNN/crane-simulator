using UnityEngine;

// MIDLERTIDIG: lokal testbevegelse.
// Erstattes av verdier fra CDP via OPC UA.
[RequireComponent(typeof(VesselController))]
public class VesselTestDriver : MonoBehaviour
{
    [SerializeField] bool enableTestMotion = true;

    [Header("Heave")]
    [SerializeField] float heaveAmplitude = 0.8f;
    [SerializeField] float heavePeriod = 8f;

    [Header("Roll")]
    [SerializeField] float rollAmplitude = 3f;
    [SerializeField] float rollPeriod = 11f;

    [Header("Pitch")]
    [SerializeField] float pitchAmplitude = 2f;
    [SerializeField] float pitchPeriod = 7f;

    VesselController vessel;

    void Awake() => vessel = GetComponent<VesselController>();

    void Update()
    {
        if (!enableTestMotion) return;

        float t = Time.time;
        vessel.heave = heaveAmplitude * Mathf.Sin(2f * Mathf.PI * t / heavePeriod);
        vessel.roll = rollAmplitude * Mathf.Sin(2f * Mathf.PI * t / rollPeriod);
        vessel.pitch = pitchAmplitude * Mathf.Sin(2f * Mathf.PI * t / pitchPeriod);
    }
}