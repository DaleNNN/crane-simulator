using UnityEngine;

public class VesselController : MonoBehaviour
{
    [Header("Translasjon (meter)")]
    public float surge;   // forover/bak
    public float sway;    // sideveis
    public float heave;   // opp/ned

    [Header("Rotasjon (grader)")]
    public float roll;
    public float pitch;
    public float yaw;

    Vector3 startPosition;

    void Start()
    {
        startPosition = transform.position;
    }

    void Update()
    {
        transform.position = startPosition + new Vector3(surge, heave, sway);
        transform.rotation = Quaternion.Euler(pitch, yaw, roll);
    }
}